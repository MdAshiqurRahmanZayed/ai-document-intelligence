import hashlib
import io
import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, DocumentStatus
from app.services import documents as service
from app.services.documents import UploadResult, ingest_upload
from tests import samples
from tests.fakes import FakeStorage, RecordingEnqueue


async def upload(
    session: AsyncSession,
    data: bytes,
    filename: str,
    storage: FakeStorage,
    enqueue: RecordingEnqueue,
    max_bytes: int = 10_000_000,
) -> UploadResult:
    return await ingest_upload(
        session=session,
        storage=storage,
        enqueue=enqueue,
        filename=filename,
        fileobj=io.BytesIO(data),
        max_bytes=max_bytes,
    )


async def load(session: AsyncSession, document_id: uuid.UUID | None) -> Document | None:
    # The service updates rows with bulk UPDATEs, which leave cached objects stale, so tests
    # re-read from the database instead of trusting the session's identity map.
    return await session.get(Document, document_id, populate_existing=True)


async def count_documents(session: AsyncSession) -> int:
    return await session.scalar(select(func.count()).select_from(Document)) or 0


async def test_accepted_file_is_stored_recorded_and_queued(session: AsyncSession) -> None:
    storage, enqueue = FakeStorage(), RecordingEnqueue()
    result = await upload(session, samples.pdf(), "invoice.pdf", storage, enqueue)

    assert result.status == "accepted"
    assert result.document_id is not None
    key = f"raw/{result.document_id}/original.pdf"
    assert storage.objects[key] == (samples.pdf(), "application/pdf")
    document = await load(session, result.document_id)
    assert document is not None
    assert document.status == DocumentStatus.QUEUED
    assert document.source_type == "pdf"
    assert enqueue.calls == [result.document_id]


@pytest.mark.parametrize(
    ("data", "filename", "source_type", "extension"),
    [
        (samples.PNG, "scan.pdf", "image", ".png"),  # an image named like a PDF
        (samples.pdf(), "scan.jpg", "pdf", ".pdf"),  # a PDF named like an image
    ],
)
async def test_wrong_extension_is_stored_by_what_the_bytes_are(
    session: AsyncSession, data: bytes, filename: str, source_type: str, extension: str
) -> None:
    storage, enqueue = FakeStorage(), RecordingEnqueue()
    result = await upload(session, data, filename, storage, enqueue)

    assert result.status == "accepted"
    document = await load(session, result.document_id)
    assert document is not None
    assert document.source_type == source_type
    assert document.storage_key == f"raw/{document.id}/original{extension}"


async def test_hash_is_correct_when_the_file_spans_several_chunks(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Small chunks force many reads. 16 bytes keeps the first chunk longer than a signature.
    monkeypatch.setattr(service, "CHUNK_SIZE", 16)
    data = samples.pdf("x" * 50)
    result = await upload(session, data, "big.pdf", FakeStorage(), RecordingEnqueue())

    document = await load(session, result.document_id)
    assert document is not None
    assert document.sha256 == hashlib.sha256(data).hexdigest()
    assert document.size == len(data)


async def test_empty_file_is_rejected(session: AsyncSession) -> None:
    storage = FakeStorage()
    result = await upload(session, b"", "empty.pdf", storage, RecordingEnqueue())

    assert (result.status, result.reason) == ("rejected", "empty_file")
    assert storage.objects == {}
    assert await count_documents(session) == 0


async def test_oversized_file_is_rejected_and_not_stored(session: AsyncSession) -> None:
    storage = FakeStorage()
    result = await upload(
        session, samples.pdf("y" * 100), "big.pdf", storage, RecordingEnqueue(), max_bytes=10
    )

    assert (result.status, result.reason) == ("rejected", "file_too_large")
    assert storage.objects == {}
    assert await count_documents(session) == 0


async def test_unsupported_type_is_rejected(session: AsyncSession) -> None:
    storage = FakeStorage()
    result = await upload(
        session, samples.zip_without_workbook(), "invoice.pdf", storage, RecordingEnqueue()
    )

    assert (result.status, result.reason) == ("rejected", "unsupported_type")
    assert storage.objects == {}


async def test_same_bytes_under_another_name_is_a_duplicate(session: AsyncSession) -> None:
    storage, enqueue = FakeStorage(), RecordingEnqueue()
    first = await upload(session, samples.pdf(), "a.pdf", storage, enqueue)
    second = await upload(session, samples.pdf(), "copy of a.pdf", storage, enqueue)

    assert second.status == "duplicate"
    assert second.document_id == first.document_id
    assert len(storage.objects) == 1
    assert enqueue.calls == [first.document_id]
    assert await count_documents(session) == 1


async def test_identical_upload_racing_the_lookup_is_resolved_by_the_constraint(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage, enqueue = FakeStorage(), RecordingEnqueue()
    first = await upload(session, samples.pdf(), "a.pdf", storage, enqueue)

    # Make the first hash lookup miss, as if the other request had not committed yet.
    real_lookup = service._find_by_hash
    calls = 0

    async def lookup(session: AsyncSession, sha256: str) -> uuid.UUID | None:
        nonlocal calls
        calls += 1
        return None if calls == 1 else await real_lookup(session, sha256)

    monkeypatch.setattr(service, "_find_by_hash", lookup)
    second = await upload(session, samples.pdf(), "b.pdf", storage, enqueue)

    assert second.status == "duplicate"
    assert second.document_id == first.document_id
    assert list(storage.objects) == [
        f"raw/{first.document_id}/original.pdf"
    ]  # loser's copy removed
    assert enqueue.calls == [first.document_id]


async def test_storage_failure_leaves_no_record(session: AsyncSession) -> None:
    result = await upload(
        session, samples.pdf(), "a.pdf", FakeStorage(fail_put=True), RecordingEnqueue()
    )

    assert (result.status, result.reason) == ("rejected", "storage_error")
    assert result.document_id is None
    assert await count_documents(session) == 0


async def test_queue_failure_keeps_a_failed_document(session: AsyncSession) -> None:
    storage = FakeStorage()
    result = await upload(session, samples.pdf(), "a.pdf", storage, RecordingEnqueue(fail=True))

    assert (result.status, result.reason) == ("rejected", "queue_unavailable")
    document = await load(session, result.document_id)
    assert document is not None
    assert document.status == DocumentStatus.FAILED
    assert document.error_code == "queue_unavailable"
    assert len(storage.objects) == 1


async def test_storage_key_ignores_the_client_filename(session: AsyncSession) -> None:
    storage = FakeStorage()
    result = await upload(session, samples.pdf(), "../../etc/passwd", storage, RecordingEnqueue())

    assert list(storage.objects) == [f"raw/{result.document_id}/original.pdf"]
    document = await load(session, result.document_id)
    assert document is not None
    assert document.filename == "../../etc/passwd"  # kept as display metadata only


async def test_reuploading_a_failed_document_retries_it(session: AsyncSession) -> None:
    storage = FakeStorage()
    failed = await upload(session, samples.pdf(), "a.pdf", storage, RecordingEnqueue(fail=True))
    assert failed.reason == "queue_unavailable"

    enqueue = RecordingEnqueue()
    retry = await upload(session, samples.pdf(), "a.pdf", storage, enqueue)

    assert retry.status == "accepted"
    assert retry.document_id == failed.document_id
    document = await load(session, failed.document_id)
    assert document is not None
    assert document.status == DocumentStatus.QUEUED
    assert document.error_code is None
    assert enqueue.calls == [failed.document_id]
    assert len(storage.objects) == 1  # the original object is reused
    assert await count_documents(session) == 1


async def test_failed_document_stays_failed_if_the_retry_cannot_be_queued(
    session: AsyncSession,
) -> None:
    storage = FakeStorage()
    first = await upload(session, samples.pdf(), "a.pdf", storage, RecordingEnqueue(fail=True))
    retry = await upload(session, samples.pdf(), "a.pdf", storage, RecordingEnqueue(fail=True))

    assert (retry.status, retry.reason) == ("rejected", "queue_unavailable")
    assert retry.document_id == first.document_id
    document = await load(session, first.document_id)
    assert document is not None
    assert (document.status, document.error_code) == (DocumentStatus.FAILED, "queue_unavailable")


async def test_only_the_first_reupload_of_a_failed_document_queues_a_job(
    session: AsyncSession,
) -> None:
    storage = FakeStorage()
    failed = await upload(session, samples.pdf(), "a.pdf", storage, RecordingEnqueue(fail=True))

    enqueue = RecordingEnqueue()
    first = await upload(session, samples.pdf(), "a.pdf", storage, enqueue)
    second = await upload(session, samples.pdf(), "a.pdf", storage, enqueue)

    assert (first.status, second.status) == ("accepted", "duplicate")
    assert second.document_id == failed.document_id
    assert enqueue.calls == [failed.document_id]
