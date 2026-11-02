import uuid
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from celery import Task
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, DocumentStatus, Page, ProcessingEvent
from tests import image_samples as images
from tests import pdf_samples as samples
from tests.fakes import FakeStorage
from tests.helpers import make_document, with_session

# These tests are synchronous on purpose: the task calls asyncio.run() itself, which cannot
# run inside pytest-asyncio's already-running loop.


@pytest.fixture
def ingest(db: str) -> Task:
    # Imported here, not at module top: importing the Celery app loads settings, which are
    # only configured once the `db` fixture has set the environment.
    from app.workers.tasks import ingest_document

    return ingest_document


@pytest.fixture
def pipeline(ingest: Task, monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[[Any], None]]:
    """Swap the placeholder pipeline for a test double."""
    # Depends on `ingest` so the environment is configured before the tasks module loads.
    import app.workers.tasks as tasks

    def install(replacement: Any) -> None:
        monkeypatch.setattr(tasks, "run_pipeline", replacement)

    yield install


@pytest.fixture
def storage(ingest: Task, monkeypatch: pytest.MonkeyPatch) -> FakeStorage:
    """In-memory bucket used by the task instead of a real S3 client."""
    import app.workers.tasks as tasks

    fake = FakeStorage()
    monkeypatch.setattr(tasks, "build_s3_storage", lambda settings: fake)
    return fake


@pytest.fixture
def ocr_queue() -> list[str]:
    """Ids of the documents the ingest job queued for OCR."""
    return []


@pytest.fixture
def ocr(ingest: Task, ocr_queue: list[str], monkeypatch: pytest.MonkeyPatch) -> Task:
    """The OCR task, with queueing replaced so ingest does not need a broker."""
    import app.workers.tasks as tasks

    monkeypatch.setattr(
        tasks.ocr_document, "delay", lambda document_id: ocr_queue.append(document_id)
    )
    return tasks.ocr_document


def queued_document(
    db: str, storage: FakeStorage | None = None, content: bytes | None = None, **fields: Any
) -> uuid.UUID:
    # Default is a spreadsheet: the pipeline does nothing for it yet, so these tests exercise
    # the task machinery without needing a stored file.
    fields.setdefault("source_type", "spreadsheet")
    fields.setdefault("status", DocumentStatus.QUEUED)
    document = make_document(**fields)
    if storage is not None and content is not None:
        storage.objects[document.storage_key] = (content, document.mime)

    async def add(session: AsyncSession) -> None:
        session.add(document)
        await session.commit()

    with_session(db, add)
    return document.id


def load(db: str, document_id: uuid.UUID) -> tuple[Document, list[ProcessingEvent]]:
    async def read(session: AsyncSession) -> tuple[Document, list[ProcessingEvent]]:
        document = await session.get(Document, document_id)
        assert document is not None
        events = (
            await session.scalars(
                select(ProcessingEvent)
                .where(ProcessingEvent.document_id == document_id)
                .order_by(ProcessingEvent.id)
            )
        ).all()
        return document, list(events)

    return with_session(db, read)


def test_successful_run_completes_and_records_events(db: str, ingest: Task) -> None:
    document_id = queued_document(db)
    ingest.apply(args=[str(document_id)])

    document, events = load(db, document_id)
    assert document.status == DocumentStatus.COMPLETED
    assert [(e.status, e.attempt) for e in events] == [("started", 1), ("succeeded", 1)]
    assert events[-1].duration_ms is not None


def test_transient_failure_is_retried_then_succeeds(
    db: str, ingest: Task, pipeline: Callable[[Any], None]
) -> None:
    attempts = 0

    async def flaky(session: AsyncSession, storage: Any, document: Document) -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("temporary glitch")

    pipeline(flaky)
    document_id = queued_document(db)
    ingest.apply(args=[str(document_id)])

    document, events = load(db, document_id)
    assert document.status == DocumentStatus.COMPLETED
    assert [(e.status, e.attempt) for e in events] == [
        ("started", 1),
        ("failed", 1),
        ("started", 2),
        ("succeeded", 2),
    ]


def test_exhausted_retries_mark_the_document_failed(
    db: str, ingest: Task, pipeline: Callable[[Any], None]
) -> None:
    async def always_fails(session: AsyncSession, storage: Any, document: Document) -> None:
        raise RuntimeError("permanent problem")

    pipeline(always_fails)
    document_id = queued_document(db)
    ingest.apply(args=[str(document_id)])

    document, events = load(db, document_id)
    assert document.status == DocumentStatus.FAILED
    assert document.error_code == "ingest_failed"
    assert document.error_message == "RuntimeError"
    failed_attempts = [e.attempt for e in events if e.status == "failed"]
    assert failed_attempts == list(range(1, ingest.max_retries + 2))  # first try + each retry


def test_missing_document_is_ignored(db: str, ingest: Task) -> None:
    result = ingest.apply(args=[str(uuid.uuid4())])

    assert result.successful()

    async def count(session: AsyncSession) -> int:
        return len((await session.scalars(select(ProcessingEvent))).all())

    assert with_session(db, count) == 0


def pdf_document(db: str, storage: FakeStorage, content: bytes) -> uuid.UUID:
    return queued_document(db, storage, content, source_type="pdf")


def page_rows(db: str, document_id: uuid.UUID) -> list[Page]:
    async def read(session: AsyncSession) -> list[Page]:
        pages = await session.scalars(select(Page).where(Page.document_id == document_id))
        return list(pages)

    return with_session(db, read)


def test_pdf_is_processed_into_pages(db: str, ingest: Task, storage: FakeStorage) -> None:
    document_id = pdf_document(db, storage, samples.text_pdf(2))
    ingest.apply(args=[str(document_id)])

    document, events = load(db, document_id)
    assert document.status == DocumentStatus.COMPLETED
    assert document.page_count == 2
    assert len(page_rows(db, document_id)) == 2
    assert [e.status for e in events] == ["started", "succeeded"]


@pytest.mark.parametrize(
    ("content", "code"),
    [
        (samples.corrupt_pdf(), "pdf_corrupt"),
        (samples.encrypted_pdf(), "pdf_encrypted"),
    ],
)
def test_unusable_pdf_fails_once_without_retry(
    db: str, ingest: Task, storage: FakeStorage, content: bytes, code: str
) -> None:
    document_id = pdf_document(db, storage, content)
    ingest.apply(args=[str(document_id)])

    document, events = load(db, document_id)
    assert document.status == DocumentStatus.FAILED
    assert document.error_code == code
    assert [(e.status, e.attempt, e.error_code) for e in events] == [
        ("started", 1, None),
        ("failed", 1, code),
    ]


def test_pdf_without_pages_fails_as_empty(
    db: str, ingest: Task, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def no_pages(session: AsyncSession, storage: Any, document: Document) -> None:
        from app.pipeline.pdf import PdfError

        raise PdfError("pdf_empty")

    import app.workers.tasks as tasks

    monkeypatch.setattr(tasks, "run_pipeline", no_pages)
    document_id = queued_document(db)
    ingest.apply(args=[str(document_id)])

    document, events = load(db, document_id)
    assert (document.status, document.error_code) == (DocumentStatus.FAILED, "pdf_empty")
    assert [e.attempt for e in events] == [1, 1]


def test_non_pdf_document_gets_no_pages(db: str, ingest: Task, storage: FakeStorage) -> None:
    document_id = queued_document(db)  # spreadsheet
    ingest.apply(args=[str(document_id)])

    document, _ = load(db, document_id)
    assert document.status == DocumentStatus.COMPLETED
    assert page_rows(db, document_id) == []


def image_document(db: str, storage: FakeStorage, content: bytes) -> uuid.UUID:
    return queued_document(db, storage, content, source_type="image", mime="image/png")


def test_image_waits_for_ocr_then_completes(
    db: str, ingest: Task, ocr: Task, ocr_queue: list[str], storage: FakeStorage
) -> None:
    document_id = image_document(db, storage, images.encode(images.text_image()))

    ingest.apply(args=[str(document_id)])

    document, events = load(db, document_id)
    assert document.status == DocumentStatus.PROCESSING  # pages are waiting for OCR
    assert ocr_queue == [str(document_id)]
    assert [(e.stage, e.status) for e in events] == [("ingest", "started"), ("ingest", "succeeded")]

    ocr.apply(args=[str(document_id)])

    document, events = load(db, document_id)
    (page,) = page_rows(db, document_id)
    assert document.status == DocumentStatus.COMPLETED
    assert page.method == "ocr" and "INVOICE" in (page.text or "")
    assert [(e.stage, e.status) for e in events[2:]] == [("ocr", "started"), ("ocr", "succeeded")]


def test_scanned_pdf_waits_for_ocr(db: str, ingest: Task, ocr: Task, storage: FakeStorage) -> None:
    document_id = pdf_document(db, storage, samples.scanned_pdf())

    ingest.apply(args=[str(document_id)])
    assert load(db, document_id)[0].status == DocumentStatus.PROCESSING

    ocr.apply(args=[str(document_id)])
    assert load(db, document_id)[0].status == DocumentStatus.COMPLETED


def test_pdf_with_text_queues_no_ocr_job(
    db: str, ingest: Task, ocr: Task, ocr_queue: list[str], storage: FakeStorage
) -> None:
    document_id = pdf_document(db, storage, samples.text_pdf(2))

    ingest.apply(args=[str(document_id)])

    assert load(db, document_id)[0].status == DocumentStatus.COMPLETED
    assert ocr_queue == []


def test_truncated_image_fails_once_without_retry(
    db: str, ingest: Task, storage: FakeStorage
) -> None:
    cut = images.truncated(images.encode(images.text_image(), "JPEG"))
    document_id = image_document(db, storage, cut)

    ingest.apply(args=[str(document_id)])

    document, events = load(db, document_id)
    assert (document.status, document.error_code) == (DocumentStatus.FAILED, "image_corrupt")
    assert [(e.status, e.attempt, e.error_code) for e in events] == [
        ("started", 1, None),
        ("failed", 1, "image_corrupt"),
    ]


def processing_document(db: str) -> uuid.UUID:
    return queued_document(db, source_type="image", status=DocumentStatus.PROCESSING)


def test_ocr_error_is_retried_then_succeeds(
    db: str, ocr: Task, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.workers.tasks as tasks

    attempts = 0

    async def flaky(session: AsyncSession, storage: Any, document: Document) -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("engine glitch")

    monkeypatch.setattr(tasks, "ocr_pages", flaky)
    monkeypatch.setattr(tasks, "build_s3_storage", lambda settings: FakeStorage())
    document_id = processing_document(db)

    ocr.apply(args=[str(document_id)])

    document, events = load(db, document_id)
    assert document.status == DocumentStatus.COMPLETED
    assert [(e.stage, e.status, e.attempt) for e in events] == [
        ("ocr", "started", 1),
        ("ocr", "failed", 1),
        ("ocr", "started", 2),
        ("ocr", "succeeded", 2),
    ]


def test_exhausted_ocr_retries_mark_the_document_failed(
    db: str, ocr: Task, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.workers.tasks as tasks

    async def always_fails(session: AsyncSession, storage: Any, document: Document) -> None:
        raise RuntimeError("engine is broken")

    monkeypatch.setattr(tasks, "ocr_pages", always_fails)
    monkeypatch.setattr(tasks, "build_s3_storage", lambda settings: FakeStorage())
    document_id = processing_document(db)

    ocr.apply(args=[str(document_id)])

    document, events = load(db, document_id)
    assert (document.status, document.error_code) == (DocumentStatus.FAILED, "ocr_failed")
    failed = [e.attempt for e in events if e.status == "failed"]
    assert failed == list(range(1, ocr.max_retries + 2))
