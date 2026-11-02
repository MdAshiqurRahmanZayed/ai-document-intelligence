import asyncio
import time
import uuid
from typing import Any

import structlog
from celery import Task
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import Document, DocumentStatus, ProcessingEvent
from app.db.session import worker_session
from app.pipeline.image import ImageError
from app.pipeline.pdf import PdfError
from app.pipeline.spreadsheet import SpreadsheetError
from app.services.image_ingest import ingest_image
from app.services.ocr_ingest import has_scanned_pages, ocr_pages
from app.services.pdf_ingest import ingest_pdf
from app.services.spreadsheet_ingest import ingest_spreadsheet
from app.services.storage import Storage, build_s3_storage
from app.workers.celery_app import celery_app

log = structlog.get_logger()

STAGE = "ingest"
OCR_STAGE = "ocr"

_UNUSABLE_MESSAGES = {
    "pdf_corrupt": "The PDF is damaged and could not be read.",
    "pdf_encrypted": "The PDF is password-protected.",
    "pdf_empty": "The PDF has no pages.",
    "image_corrupt": "The image is damaged and could not be read.",
    "spreadsheet_corrupt": "The spreadsheet is damaged and could not be read.",
    "spreadsheet_empty": "The spreadsheet has no data.",
}

# Both jobs retry the same way: a few attempts with growing pauses.
_RETRY = {
    "autoretry_for": (Exception,),
    "retry_backoff": True,  # 1s, 2s, 4s ... between attempts
    "retry_backoff_max": 60,
    "retry_jitter": True,  # spreads retries so failing jobs do not all return at once
    "max_retries": 3,
}


async def run_pipeline(session: AsyncSession, storage: Storage, document: Document) -> bool:
    """Dispatch by document type. Returns True when pages still need OCR."""
    if document.source_type == "pdf":
        await ingest_pdf(session, storage, document)
    elif document.source_type == "image":
        await ingest_image(session, storage, document)
    elif document.source_type == "spreadsheet":
        await ingest_spreadsheet(session, storage, document)
        return False  # spreadsheet pages are text from the start, so nothing to OCR
    else:
        return False
    return await has_scanned_pages(session, document)


class IngestTask(Task):
    def on_failure(
        self,
        exc: Exception,
        task_id: str,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        einfo: Any,
    ) -> None:
        # Celery calls this only after the last retry has failed.
        asyncio.run(_mark_failed(uuid.UUID(args[0]), exc, "ingest_failed"))


class OcrTask(Task):
    def on_failure(
        self,
        exc: Exception,
        task_id: str,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        einfo: Any,
    ) -> None:
        asyncio.run(_mark_failed(uuid.UUID(args[0]), exc, "ocr_failed"))


@celery_app.task(bind=True, base=IngestTask, name="app.workers.ingest_document", **_RETRY)
def ingest_document(self: Task, document_id: str) -> None:
    asyncio.run(_run(uuid.UUID(document_id), attempt=self.request.retries + 1))


# Own queue: OCR is slow and must not hold up ingest jobs queued behind it.
@celery_app.task(bind=True, base=OcrTask, name="app.workers.ocr_document", queue="ocr", **_RETRY)
def ocr_document(self: Task, document_id: str) -> None:
    asyncio.run(_run_ocr(uuid.UUID(document_id), attempt=self.request.retries + 1))


async def _run(document_id: uuid.UUID, attempt: int) -> None:
    async with worker_session() as session:
        document = await session.get(Document, document_id)
        if document is None:
            return  # deleted before the job ran; nothing to do and nothing to retry

        started = time.perf_counter()
        document.status = DocumentStatus.PROCESSING
        session.add(_event(document_id, "started", attempt))
        await session.commit()

        try:
            ocr_pending = await run_pipeline(session, build_s3_storage(get_settings()), document)
        except (PdfError, ImageError, SpreadsheetError) as exc:
            # The file itself is unusable, so retrying cannot help: fail now and do not re-raise
            # (re-raising would hand it to Celery's retry policy).
            log.warning("file_unusable", document_id=str(document_id), code=exc.code)
            document.status = DocumentStatus.FAILED
            document.error_code = exc.code
            document.error_message = _UNUSABLE_MESSAGES[exc.code]
            session.add(_event(document_id, "failed", attempt, started, exc.code, exc.code))
            await session.commit()
            return
        except Exception as exc:
            # Record the attempt, then re-raise so Celery's retry policy takes over.
            log.exception("ingest_attempt_failed", document_id=str(document_id), attempt=attempt)
            session.add(
                _event(document_id, "failed", attempt, started, "ingest_failed", type(exc).__name__)
            )
            await session.commit()
            raise

        # With pages waiting for OCR the document stays PROCESSING; the OCR job completes it.
        if not ocr_pending:
            document.status = DocumentStatus.COMPLETED
        session.add(_event(document_id, "succeeded", attempt, started))
        await session.commit()
        if ocr_pending:
            # After the commit, so the OCR job always finds the saved pages. If queueing fails
            # the exception retries this whole (idempotent) job.
            ocr_document.delay(str(document_id))


async def _run_ocr(document_id: uuid.UUID, attempt: int) -> None:
    async with worker_session() as session:
        document = await session.get(Document, document_id)
        if document is None:
            return

        started = time.perf_counter()
        session.add(_event(document_id, "started", attempt, stage=OCR_STAGE))
        await session.commit()

        try:
            await ocr_pages(session, build_s3_storage(get_settings()), document)
        except Exception as exc:
            log.exception("ocr_attempt_failed", document_id=str(document_id), attempt=attempt)
            session.add(
                _event(
                    document_id,
                    "failed",
                    attempt,
                    started,
                    "ocr_failed",
                    type(exc).__name__,
                    stage=OCR_STAGE,
                )
            )
            await session.commit()
            raise

        document.status = DocumentStatus.COMPLETED
        session.add(_event(document_id, "succeeded", attempt, started, stage=OCR_STAGE))
        await session.commit()


async def _mark_failed(document_id: uuid.UUID, exc: Exception, code: str) -> None:
    async with worker_session() as session:
        document = await session.get(Document, document_id)
        if document is None:
            return
        document.status = DocumentStatus.FAILED
        document.error_code = code
        # Only the exception type: the full detail is in the logs and may contain internals.
        document.error_message = type(exc).__name__
        await session.commit()


def _event(
    document_id: uuid.UUID,
    status: str,
    attempt: int,
    started: float | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
    stage: str = STAGE,
) -> ProcessingEvent:
    return ProcessingEvent(
        document_id=document_id,
        stage=stage,
        status=status,
        attempt=attempt,
        duration_ms=None if started is None else round((time.perf_counter() - started) * 1000),
        error_code=error_code,
        error_message=error_message,
    )
