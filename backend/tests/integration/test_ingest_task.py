import uuid
from collections.abc import Callable, Iterator, Sequence
from typing import Any

import pytest
from celery import Task
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import Chunk, Document, DocumentStatus, Page, ProcessingEvent
from app.llm.embeddings import Embedder
from app.llm.extract import ExtractedInvoice, InvoiceExtractor
from tests import image_samples as images
from tests import pdf_samples as samples
from tests import spreadsheet_samples as sheets
from tests.fake_embedder import FakeEmbedder
from tests.fakes import FakeStorage
from tests.helpers import make_document, run_sync, with_session
from tests.invoice_fakes import TEXT, FakeExtractor, draft

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
    # No stored file by default: tests that use a bare document replace `run_pipeline`.
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


def test_successful_run_completes_and_records_events(
    db: str, ingest: Task, pipeline: Callable[[Any], None]
) -> None:
    async def nothing_to_do(session: AsyncSession, storage: Any, document: Document) -> bool:
        return False

    pipeline(nothing_to_do)
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


XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def spreadsheet_document(db: str, storage: FakeStorage, content: bytes) -> uuid.UUID:
    return queued_document(
        db, storage, content, source_type="spreadsheet", mime=XLSX_MIME, filename="inv.xlsx"
    )


def test_spreadsheet_is_completed_with_pages_and_no_ocr_job(
    db: str, ingest: Task, ocr: Task, ocr_queue: list[str], storage: FakeStorage
) -> None:
    document_id = spreadsheet_document(db, storage, sheets.multi_sheet_xlsx())

    ingest.apply(args=[str(document_id)])

    document, events = load(db, document_id)
    assert document.status == DocumentStatus.COMPLETED
    assert [p.method for p in page_rows(db, document_id)] == ["native", "native"]
    assert [(e.stage, e.status) for e in events] == [("ingest", "started"), ("ingest", "succeeded")]
    assert ocr_queue == []


@pytest.mark.parametrize(
    ("content", "code"),
    [
        (sheets.truncated(sheets.multi_sheet_xlsx()), "spreadsheet_corrupt"),
        (sheets.empty_xlsx(), "spreadsheet_empty"),
    ],
)
def test_unusable_spreadsheet_fails_once_without_retry(
    db: str, ingest: Task, storage: FakeStorage, content: bytes, code: str
) -> None:
    document_id = spreadsheet_document(db, storage, content)

    ingest.apply(args=[str(document_id)])

    document, events = load(db, document_id)
    assert (document.status, document.error_code) == (DocumentStatus.FAILED, code)
    assert [(e.status, e.attempt, e.error_code) for e in events] == [
        ("started", 1, None),
        ("failed", 1, code),
    ]
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

    async def flaky(
        session: AsyncSession, storage: Any, document: Document, concurrency: int
    ) -> None:
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

    async def always_fails(
        session: AsyncSession, storage: Any, document: Document, concurrency: int
    ) -> None:
        raise RuntimeError("engine is broken")

    monkeypatch.setattr(tasks, "ocr_pages", always_fails)
    monkeypatch.setattr(tasks, "build_s3_storage", lambda settings: FakeStorage())
    document_id = processing_document(db)

    ocr.apply(args=[str(document_id)])

    document, events = load(db, document_id)
    assert (document.status, document.error_code) == (DocumentStatus.FAILED, "ocr_failed")
    failed = [e.attempt for e in events if e.status == "failed"]
    assert failed == list(range(1, ocr.max_retries + 2))


@pytest.mark.parametrize(
    ("source_type", "expected"),
    [("pdf", "ingest_pdf"), ("image", "ingest_image"), ("spreadsheet", "ingest_spreadsheet")],
)
def test_each_file_type_is_routed_to_its_own_ingest(
    ingest: Task, monkeypatch: pytest.MonkeyPatch, source_type: str, expected: str
) -> None:
    import app.workers.tasks as tasks

    called: list[str] = []

    def stub(name: str) -> Callable[..., Any]:
        async def fake(*args: Any) -> None:
            called.append(name)

        return fake

    for name in ("ingest_pdf", "ingest_image", "ingest_spreadsheet"):
        monkeypatch.setattr(tasks, name, stub(name))

    async def no_scanned_pages(*args: Any) -> bool:
        return False

    monkeypatch.setattr(tasks, "has_scanned_pages", no_scanned_pages)

    unused: Any = None  # the stubs never touch the session or storage
    run_sync(tasks.run_pipeline(unused, unused, make_document(source_type=source_type)))

    assert called == [expected]


# --- extraction after the text is ready ---------------------------------------------------


@pytest.fixture
def embed_queue(ingest: Task, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Ids of the documents queued for embedding, instead of sending them to a broker."""
    import app.workers.tasks as tasks

    queued: list[str] = []
    monkeypatch.setattr(
        tasks.embed_document, "delay", lambda document_id: queued.append(document_id)
    )
    return queued


@pytest.fixture
def with_api_key(ingest: Task, embed_queue: list[str], monkeypatch: pytest.MonkeyPatch) -> None:
    """Turn extraction on: it only runs when a Google API key is configured."""
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    get_settings.cache_clear()  # settings are cached; the `db` fixture clears them again after


@pytest.fixture
def extract_queue(ingest: Task, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Ids of the documents queued for extraction, instead of sending them to a broker."""
    import app.workers.tasks as tasks

    queued: list[str] = []
    monkeypatch.setattr(
        tasks.extract_document, "delay", lambda document_id: queued.append(document_id)
    )
    return queued


@pytest.fixture
def extract(ingest: Task) -> Task:
    import app.workers.tasks as tasks

    return tasks.extract_document


def use_extractor(monkeypatch: pytest.MonkeyPatch, extractor: InvoiceExtractor) -> None:
    import app.workers.tasks as tasks

    monkeypatch.setattr(tasks, "build_extractor", lambda settings: extractor)


def document_with_text(db: str, text: str = TEXT) -> uuid.UUID:
    """A document whose text is ready: the state in which the extraction job starts."""
    document_id = queued_document(db, source_type="pdf", status=DocumentStatus.PROCESSING)

    async def add_page(session: AsyncSession) -> None:
        session.add(Page(document_id=document_id, page_no=1, text=text, method="native"))
        await session.commit()

    with_session(db, add_page)
    return document_id


def test_with_a_key_a_text_document_waits_for_extraction(
    db: str,
    ingest: Task,
    with_api_key: None,
    extract_queue: list[str],
    storage: FakeStorage,
) -> None:
    document_id = pdf_document(db, storage, samples.text_pdf(2))

    ingest.apply(args=[str(document_id)])

    document, events = load(db, document_id)
    assert document.status == DocumentStatus.PROCESSING
    assert extract_queue == [str(document_id)]
    assert [(e.stage, e.status) for e in events] == [("ingest", "started"), ("ingest", "succeeded")]


def test_a_scanned_document_is_extracted_only_after_ocr(
    db: str,
    ingest: Task,
    ocr: Task,
    ocr_queue: list[str],
    with_api_key: None,
    extract_queue: list[str],
    storage: FakeStorage,
) -> None:
    document_id = image_document(db, storage, images.encode(images.text_image()))

    ingest.apply(args=[str(document_id)])
    assert ocr_queue == [str(document_id)] and extract_queue == []

    ocr.apply(args=[str(document_id)])

    assert extract_queue == [str(document_id)]
    assert load(db, document_id)[0].status == DocumentStatus.PROCESSING


def test_without_a_key_nothing_is_queued_for_extraction(
    db: str, ingest: Task, extract_queue: list[str], storage: FakeStorage
) -> None:
    document_id = pdf_document(db, storage, samples.text_pdf(2))

    ingest.apply(args=[str(document_id)])

    assert extract_queue == []
    assert load(db, document_id)[0].status == DocumentStatus.COMPLETED


def test_the_extract_job_completes_the_document_and_records_its_events(
    db: str, extract: Task, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_extractor(monkeypatch, FakeExtractor([draft()]))
    document_id = document_with_text(db)

    extract.apply(args=[str(document_id)])

    document, events = load(db, document_id)
    assert document.status == DocumentStatus.COMPLETED
    assert [(e.stage, e.status, e.attempt) for e in events] == [
        ("extract", "started", 1),
        ("extract", "succeeded", 1),
    ]


def test_validation_can_send_the_document_for_review(
    db: str, extract: Task, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_extractor(monkeypatch, FakeExtractor([draft(total="130.00")], TEXT + "\nTotal 130.00"))
    document_id = document_with_text(db, TEXT + "\nTotal 130.00")

    extract.apply(args=[str(document_id)])

    assert load(db, document_id)[0].status == DocumentStatus.NEEDS_REVIEW


class FlakyExtractor(FakeExtractor):
    """Fails the first `failures` calls, then behaves like FakeExtractor."""

    def __init__(self, failures: int) -> None:
        super().__init__([draft()])
        self.failures = failures

    def extract(self, pages: Sequence[tuple[int, str]]) -> list[ExtractedInvoice]:
        if self.failures > 0:
            self.failures -= 1
            raise RuntimeError("model is down")
        return super().extract(pages)


def test_a_model_error_is_retried_then_succeeds(
    db: str, extract: Task, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_extractor(monkeypatch, FlakyExtractor(failures=1))
    document_id = document_with_text(db)

    extract.apply(args=[str(document_id)])

    document, events = load(db, document_id)
    assert document.status == DocumentStatus.COMPLETED
    assert [(e.status, e.attempt) for e in events] == [
        ("started", 1),
        ("failed", 1),
        ("started", 2),
        ("succeeded", 2),
    ]


def test_exhausted_extraction_retries_fail_the_document(
    db: str, extract: Task, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_extractor(monkeypatch, FlakyExtractor(failures=99))
    document_id = document_with_text(db)

    extract.apply(args=[str(document_id)])

    document, events = load(db, document_id)
    assert (document.status, document.error_code) == (DocumentStatus.FAILED, "extraction_failed")
    assert document.error_message == "RuntimeError"
    failed = [e.attempt for e in events if e.status == "failed" and e.stage == "extract"]
    assert failed == list(range(1, extract.max_retries + 2))


# --- indexing and embeddings ----------------------------------------------------------------


def chunk_rows(db: str, document_id: uuid.UUID) -> list[Chunk]:
    async def read(session: AsyncSession) -> list[Chunk]:
        rows = await session.scalars(
            select(Chunk).where(Chunk.document_id == document_id).order_by(Chunk.id)
        )
        return list(rows)

    return with_session(db, read)


def add_chunks(db: str, document_id: uuid.UUID, *texts: str) -> None:
    async def add(session: AsyncSession) -> None:
        session.add_all(
            Chunk(document_id=document_id, page_no=1, chunk_no=n, text=text)
            for n, text in enumerate(texts)
        )
        await session.commit()

    with_session(db, add)


@pytest.fixture
def embed(ingest: Task) -> Task:
    import app.workers.tasks as tasks

    return tasks.embed_document


def use_embedder(monkeypatch: pytest.MonkeyPatch, embedder: Embedder) -> None:
    import app.workers.tasks as tasks

    monkeypatch.setattr(tasks, "build_embedder", lambda settings: embedder)


def test_a_text_pdf_is_indexed_when_it_is_ingested(
    db: str, ingest: Task, storage: FakeStorage
) -> None:
    document_id = pdf_document(db, storage, samples.text_pdf(2))

    ingest.apply(args=[str(document_id)])

    chunks = chunk_rows(db, document_id)
    assert [c.page_no for c in chunks] == [1, 2]
    assert "Invoice number 1042" in chunks[0].text


def test_a_scanned_image_is_indexed_only_after_ocr(
    db: str, ingest: Task, ocr: Task, storage: FakeStorage
) -> None:
    document_id = image_document(db, storage, images.encode(images.text_image()))

    ingest.apply(args=[str(document_id)])
    assert chunk_rows(db, document_id) == []  # no text yet

    ocr.apply(args=[str(document_id)])

    chunks = chunk_rows(db, document_id)
    assert chunks and "INVOICE" in chunks[0].text


def test_a_spreadsheet_is_indexed(db: str, ingest: Task, storage: FakeStorage) -> None:
    document_id = spreadsheet_document(db, storage, sheets.multi_sheet_xlsx())

    ingest.apply(args=[str(document_id)])

    assert [c.text.splitlines()[0] for c in chunk_rows(db, document_id)] == [
        "Sheet: Invoices",
        "Sheet: Merged",
    ]


def test_without_a_key_no_embedding_job_is_queued(
    db: str, ingest: Task, embed_queue: list[str], storage: FakeStorage
) -> None:
    document_id = pdf_document(db, storage, samples.text_pdf(1))

    ingest.apply(args=[str(document_id)])

    assert embed_queue == [] and chunk_rows(db, document_id)  # indexed, but not embedded


def test_with_a_key_embedding_is_queued_once_the_text_is_ready(
    db: str,
    ingest: Task,
    ocr: Task,
    ocr_queue: list[str],
    with_api_key: None,
    embed_queue: list[str],
    extract_queue: list[str],
    storage: FakeStorage,
) -> None:
    text_doc = pdf_document(db, storage, samples.text_pdf(1))
    scanned = image_document(db, storage, images.encode(images.text_image()))

    ingest.apply(args=[str(text_doc)])
    assert embed_queue == [str(text_doc)]  # right after ingest, alongside extraction

    ingest.apply(args=[str(scanned)])
    assert embed_queue == [str(text_doc)]  # not yet: this one still needs OCR
    ocr.apply(args=[str(scanned)])
    assert embed_queue == [str(text_doc), str(scanned)]


def test_the_embed_job_fills_the_embeddings_and_leaves_the_status_alone(
    db: str, embed: Task, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_embedder(monkeypatch, FakeEmbedder())
    document_id = queued_document(db, source_type="pdf", status=DocumentStatus.COMPLETED)
    add_chunks(db, document_id, "payment due", "delivery soon")

    embed.apply(args=[str(document_id)])

    assert all(c.embedding is not None for c in chunk_rows(db, document_id))
    document, events = load(db, document_id)
    assert document.status == DocumentStatus.COMPLETED
    assert [(e.stage, e.status) for e in events] == [("embed", "started"), ("embed", "succeeded")]


class FlakyEmbedder(FakeEmbedder):
    """Fails the first `failures` calls, then embeds normally."""

    def __init__(self, failures: int) -> None:
        super().__init__()
        self.failures = failures

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        if self.failures > 0:
            self.failures -= 1
            raise RuntimeError("embedding model is down")
        return super().embed_documents(texts)


def test_an_embedding_error_is_retried_then_succeeds(
    db: str, embed: Task, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_embedder(monkeypatch, FlakyEmbedder(failures=1))
    document_id = queued_document(db, source_type="pdf", status=DocumentStatus.COMPLETED)
    add_chunks(db, document_id, "payment due")

    embed.apply(args=[str(document_id)])

    _, events = load(db, document_id)
    assert [(e.status, e.attempt) for e in events] == [
        ("started", 1),
        ("failed", 1),
        ("started", 2),
        ("succeeded", 2),
    ]
    assert chunk_rows(db, document_id)[0].embedding is not None


def test_exhausted_embedding_retries_are_recorded_and_the_document_is_untouched(
    db: str, embed: Task, monkeypatch: pytest.MonkeyPatch
) -> None:
    use_embedder(monkeypatch, FlakyEmbedder(failures=99))
    document_id = queued_document(db, source_type="pdf", status=DocumentStatus.COMPLETED)
    add_chunks(db, document_id, "payment due")

    embed.apply(args=[str(document_id)])

    document, events = load(db, document_id)
    failed = [e.attempt for e in events if e.status == "failed" and e.stage == "embed"]
    assert failed == list(range(1, embed.max_retries + 2))
    assert (document.status, document.error_code) == (DocumentStatus.COMPLETED, None)
    assert chunk_rows(db, document_id)[0].embedding is None  # still found by keyword search
