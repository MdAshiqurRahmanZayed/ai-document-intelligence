import asyncio
import time
import uuid
from typing import Any

import structlog
from celery import Task

from app.db.models import Document, DocumentStatus, ProcessingEvent
from app.db.session import worker_session
from app.workers.celery_app import celery_app

log = structlog.get_logger()

STAGE = "ingest"


async def run_pipeline(document: Document) -> None:
    """Extension point. Later changes (PDF, OCR, spreadsheets) plug their work in here."""


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
        asyncio.run(_mark_failed(uuid.UUID(args[0]), exc))


@celery_app.task(
    bind=True,
    base=IngestTask,
    name="app.workers.ingest_document",
    autoretry_for=(Exception,),
    retry_backoff=True,  # 1s, 2s, 4s ... between attempts
    retry_backoff_max=60,
    retry_jitter=True,  # spreads retries so failing jobs do not all return at once
    max_retries=3,
)
def ingest_document(self: Task, document_id: str) -> None:
    asyncio.run(_run(uuid.UUID(document_id), attempt=self.request.retries + 1))


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
            await run_pipeline(document)
        except Exception as exc:
            # Record the attempt, then re-raise so Celery's retry policy takes over.
            log.exception("ingest_attempt_failed", document_id=str(document_id), attempt=attempt)
            session.add(_event(document_id, "failed", attempt, started, exc))
            await session.commit()
            raise

        document.status = DocumentStatus.COMPLETED
        session.add(_event(document_id, "succeeded", attempt, started))
        await session.commit()


async def _mark_failed(document_id: uuid.UUID, exc: Exception) -> None:
    async with worker_session() as session:
        document = await session.get(Document, document_id)
        if document is None:
            return
        document.status = DocumentStatus.FAILED
        document.error_code = "ingest_failed"
        # Only the exception type: the full detail is in the logs and may contain internals.
        document.error_message = type(exc).__name__
        await session.commit()


def _event(
    document_id: uuid.UUID,
    status: str,
    attempt: int,
    started: float | None = None,
    exc: Exception | None = None,
) -> ProcessingEvent:
    return ProcessingEvent(
        document_id=document_id,
        stage=STAGE,
        status=status,
        attempt=attempt,
        duration_ms=None if started is None else round((time.perf_counter() - started) * 1000),
        error_code=None if exc is None else "ingest_failed",
        error_message=None if exc is None else type(exc).__name__,
    )
