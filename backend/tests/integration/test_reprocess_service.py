import asyncio
import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.db.models import Document, DocumentStatus, Extraction, Page, ProcessingEvent
from app.services.errors import DocumentNotFound
from app.services.reprocess import (
    AlreadyQueued,
    CannotReprocess,
    QueueUnavailable,
    Reprocessed,
    RetryResult,
    Stage,
    reprocess_document,
    retry_failed,
)
from tests.fakes import RecordingEnqueue
from tests.helpers import make_document
from tests.invoice_fakes import draft, extracted_document


class Queues:
    """The two job hooks, recording what was queued, with the service calls wrapped."""

    def __init__(self, fail: bool = False) -> None:
        self.ingest = RecordingEnqueue(fail=fail)
        self.extract = RecordingEnqueue(fail=fail)

    async def reprocess(
        self,
        session: AsyncSession,
        document_id: uuid.UUID,
        stage: Stage = "ingest",
        *,
        extraction: bool = True,
    ) -> Reprocessed:
        return await reprocess_document(
            session,
            document_id,
            stage,
            extraction_enabled=extraction,
            enqueue=self.ingest,
            enqueue_extract=self.extract,
        )

    async def retry(self, session: AsyncSession, limit: int = 100) -> RetryResult:
        return await retry_failed(
            session,
            limit,
            extraction_enabled=True,
            enqueue=self.ingest,
            enqueue_extract=self.extract,
        )


async def document(
    session: AsyncSession, status: str, error_code: str | None = None, text: str | None = None
) -> Document:
    doc = make_document(status=status, error_code=error_code)
    session.add(doc)
    await session.commit()
    if text is not None:
        session.add(Page(document_id=doc.id, page_no=1, text=text, method="native"))
        await session.commit()
    return doc


async def reload(session: AsyncSession, doc: Document) -> Document:
    await session.refresh(doc)
    return doc


async def test_a_failed_document_is_queued_once_and_its_error_is_cleared(
    session: AsyncSession,
) -> None:
    doc = await document(session, DocumentStatus.FAILED, "ingest_failed")
    queues = Queues()

    result = await queues.reprocess(session, doc.id, "ingest")

    assert (result.status, result.from_stage) == ("QUEUED", "ingest")
    doc = await reload(session, doc)
    assert (doc.status, doc.error_code, doc.error_message) == (DocumentStatus.QUEUED, None, None)
    assert queues.ingest.calls == [doc.id] and queues.extract.calls == []


@pytest.mark.parametrize("status", [DocumentStatus.NEEDS_REVIEW, DocumentStatus.COMPLETED])
async def test_finished_documents_can_be_run_again(
    session: AsyncSession, status: DocumentStatus
) -> None:
    doc = await document(session, status)
    queues = Queues()

    await queues.reprocess(session, doc.id, "ingest")

    assert queues.ingest.calls == [doc.id]


async def test_extract_queues_only_the_extraction_job(session: AsyncSession) -> None:
    doc = await document(session, DocumentStatus.NEEDS_REVIEW, text="Invoice INV-1")
    queues = Queues()

    result = await queues.reprocess(session, doc.id, "extract")

    assert result.from_stage == "extract"
    assert queues.extract.calls == [doc.id] and queues.ingest.calls == []


async def test_extract_needs_text_and_a_key_and_leaves_the_document_alone(
    session: AsyncSession,
) -> None:
    no_text = await document(session, DocumentStatus.FAILED, "ocr_failed", text="")
    queues = Queues()

    with pytest.raises(CannotReprocess) as blank:
        await queues.reprocess(session, no_text.id, "extract")
    with_text = await document(session, DocumentStatus.FAILED, "extraction_failed", text="x")
    with pytest.raises(CannotReprocess) as disabled:
        await queues.reprocess(session, with_text.id, "extract", extraction=False)

    assert (blank.value.reason, disabled.value.reason) == ("no_text", "extraction_disabled")
    assert (await reload(session, no_text)).status == DocumentStatus.FAILED
    assert (await reload(session, with_text)).error_code == "extraction_failed"
    assert queues.ingest.calls == [] and queues.extract.calls == []


@pytest.mark.parametrize(
    "status", [DocumentStatus.UPLOADED, DocumentStatus.QUEUED, DocumentStatus.PROCESSING]
)
async def test_a_document_that_is_waiting_or_running_is_refused(
    session: AsyncSession, status: DocumentStatus
) -> None:
    doc = await document(session, status)
    queues = Queues()

    with pytest.raises(AlreadyQueued):
        await queues.reprocess(session, doc.id, "ingest")

    assert queues.ingest.calls == [] and (await reload(session, doc)).status == status


async def test_an_unknown_document_is_not_found(session: AsyncSession) -> None:
    with pytest.raises(DocumentNotFound):
        await Queues().reprocess(session, uuid.uuid4())


async def test_two_requests_at_once_queue_exactly_one_job(db: str, session: AsyncSession) -> None:
    doc = await document(session, DocumentStatus.FAILED, "ingest_failed")
    queues = Queues()
    engine = create_async_engine(db, poolclass=NullPool)
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def attempt() -> str:
        async with sessions() as own:
            try:
                await queues.reprocess(own, doc.id)
            except AlreadyQueued:
                return "refused"
            return "queued"

    outcomes = await asyncio.gather(attempt(), attempt())
    await engine.dispose()

    assert sorted(outcomes) == ["queued", "refused"]
    assert queues.ingest.calls == [doc.id]


async def test_a_broker_error_ends_the_document_failed_so_it_can_be_retried(
    session: AsyncSession,
) -> None:
    doc = await document(session, DocumentStatus.FAILED, "ingest_failed")

    with pytest.raises(QueueUnavailable):
        await Queues(fail=True).reprocess(session, doc.id)

    doc = await reload(session, doc)
    assert (doc.status, doc.error_code) == (DocumentStatus.FAILED, "queue_unavailable")


async def test_history_and_earlier_versions_survive(session: AsyncSession) -> None:
    doc = await extracted_document(session, [draft()])
    session.add(ProcessingEvent(document_id=doc.id, stage="ingest", status="succeeded", attempt=1))
    await session.commit()

    await Queues().reprocess(session, doc.id, "extract")

    events = await session.scalar(select(func.count()).select_from(ProcessingEvent))
    saved = await session.scalar(select(func.count()).select_from(Extraction))
    assert (events, saved) == (1, 1)


async def test_retry_failed_uses_the_stage_that_failed(session: AsyncSession) -> None:
    broken_model = await document(session, DocumentStatus.FAILED, "extraction_failed", text="x")
    broken_file = await document(session, DocumentStatus.FAILED, "pdf_corrupt")
    broken_job = await document(session, DocumentStatus.FAILED, "ingest_failed")
    await document(session, DocumentStatus.COMPLETED)  # not failed: left alone
    queues = Queues()

    result = await queues.retry(session, 100)

    assert result.queued == [broken_model.id, broken_file.id, broken_job.id]  # oldest first
    assert result.not_queued == 0
    assert queues.extract.calls == [broken_model.id]
    assert queues.ingest.calls == [broken_file.id, broken_job.id]


async def test_retry_failed_honours_the_limit_and_the_order(session: AsyncSession) -> None:
    failed = [await document(session, DocumentStatus.FAILED, "ingest_failed") for _ in range(5)]
    queues = Queues()

    result = await queues.retry(session, 2)

    assert result.queued == [failed[0].id, failed[1].id]
    left = [(await reload(session, d)).status for d in failed[2:]]
    assert left == [DocumentStatus.FAILED] * 3


async def test_retry_failed_does_nothing_when_nothing_failed(session: AsyncSession) -> None:
    await document(session, DocumentStatus.COMPLETED)
    queues = Queues()

    result = await queues.retry(session, 100)

    assert (result.queued, result.not_queued) == ([], 0)
    assert queues.ingest.calls == [] and queues.extract.calls == []


async def test_retry_failed_counts_documents_it_could_not_queue(session: AsyncSession) -> None:
    await document(session, DocumentStatus.FAILED, "ingest_failed")

    result = await Queues(fail=True).retry(session)

    assert (result.queued, result.not_queued) == ([], 1)
