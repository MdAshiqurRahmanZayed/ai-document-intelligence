"""Run a document through the pipeline again, one at a time or all failed ones."""

import asyncio
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, DocumentStatus, Page
from app.services.errors import DocumentNotFound

log = structlog.get_logger()

Stage = Literal["ingest", "extract"]
Enqueue = Callable[[uuid.UUID], None]
# A document being worked on, or waiting for a worker, is never queued a second time.
REPROCESSABLE = (DocumentStatus.FAILED, DocumentStatus.NEEDS_REVIEW, DocumentStatus.COMPLETED)


class AlreadyQueued(Exception):
    pass


class CannotReprocess(Exception):
    """The requested stage cannot run. `reason` is `no_text` or `extraction_disabled`."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class QueueUnavailable(Exception):
    pass


@dataclass(frozen=True)
class Reprocessed:
    document_id: uuid.UUID
    status: str
    from_stage: Stage


@dataclass(frozen=True)
class RetryResult:
    queued: list[uuid.UUID]
    not_queued: int


async def reprocess_document(
    session: AsyncSession,
    document_id: uuid.UUID,
    from_stage: Stage,
    *,
    extraction_enabled: bool,
    enqueue: Enqueue,
    enqueue_extract: Enqueue,
) -> Reprocessed:
    """Queue the document again: the whole pipeline (`ingest`) or extraction only (`extract`).

    History, earlier invoice versions and corrections are kept.
    """
    if await session.get(Document, document_id) is None:
        raise DocumentNotFound(document_id)
    if from_stage == "extract":
        if not extraction_enabled:
            raise CannotReprocess("extraction_disabled")
        has_text = await session.scalar(
            select(Page.id)
            .where(Page.document_id == document_id, Page.text.is_not(None), Page.text != "")
            .limit(1)
        )
        if has_text is None:
            raise CannotReprocess("no_text")

    # The UPDATE only matches while the document is in a reprocessable status, so when several
    # requests arrive together exactly one claims it and queues the job; the rest are refused.
    claimed = await session.scalar(
        update(Document)
        .where(Document.id == document_id, Document.status.in_(REPROCESSABLE))
        .values(status=DocumentStatus.QUEUED, error_code=None, error_message=None)
        .returning(Document.id)
    )
    await session.commit()
    if claimed is None:
        raise AlreadyQueued

    try:
        # .delay() is blocking network I/O, so it runs off the event loop.
        await asyncio.to_thread(enqueue if from_stage == "ingest" else enqueue_extract, document_id)
    except Exception:
        log.exception("enqueue_failed", document_id=str(document_id), stage=from_stage)
        await session.execute(
            update(Document)
            .where(Document.id == document_id)
            .values(
                status=DocumentStatus.FAILED,
                error_code="queue_unavailable",
                error_message="Could not hand the document to the processing queue.",
            )
        )
        await session.commit()
        raise QueueUnavailable from None
    return Reprocessed(document_id, DocumentStatus.QUEUED, from_stage)


async def retry_failed(
    session: AsyncSession,
    limit: int,
    *,
    extraction_enabled: bool,
    enqueue: Enqueue,
    enqueue_extract: Enqueue,
) -> RetryResult:
    """Queue the oldest failed documents again, each from the stage that failed."""
    rows = await session.execute(
        select(Document.id, Document.error_code)
        .where(Document.status == DocumentStatus.FAILED)
        .order_by(Document.created_at, Document.id)
        .limit(limit)
    )
    queued: list[uuid.UUID] = []
    not_queued = 0
    for document_id, error_code in rows.all():
        stage: Stage = (
            "extract" if error_code == "extraction_failed" and extraction_enabled else "ingest"
        )
        try:
            await reprocess_document(
                session,
                document_id,
                stage,
                extraction_enabled=extraction_enabled,
                enqueue=enqueue,
                enqueue_extract=enqueue_extract,
            )
        except (AlreadyQueued, CannotReprocess, QueueUnavailable):
            not_queued += 1
        else:
            queued.append(document_id)
    return RetryResult(queued, not_queued)
