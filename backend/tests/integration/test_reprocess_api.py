import uuid
from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.models import Document, DocumentStatus, Page
from tests.helpers import Api, make_document, running_api


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


def url(document_id: uuid.UUID) -> str:
    return f"/api/v1/documents/{document_id}/reprocess"


@pytest.fixture
async def keyed(db: str, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Api]:
    """An app with a Google API key set, so that extraction is enabled."""
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    async with running_api(Settings()) as running:
        yield running


async def test_reprocess_queues_the_document_and_returns_202(
    api: Api, session: AsyncSession
) -> None:
    doc = await document(session, DocumentStatus.FAILED, "ingest_failed")

    response = await api.client.post(url(doc.id))

    assert response.status_code == 202
    assert response.json() == {
        "document_id": str(doc.id),
        "status": "QUEUED",
        "from_stage": "ingest",
    }
    assert api.enqueue.calls == [doc.id] and api.enqueue_extract.calls == []
    detail = (await api.client.get(f"/api/v1/documents/{doc.id}")).json()
    assert (detail["status"], detail["error_code"]) == ("QUEUED", None)


async def test_extract_stage_queues_only_extraction(keyed: Api, session: AsyncSession) -> None:
    doc = await document(session, DocumentStatus.NEEDS_REVIEW, text="Invoice INV-1")

    response = await keyed.client.post(url(doc.id), json={"from_stage": "extract"})

    assert response.status_code == 202 and response.json()["from_stage"] == "extract"
    assert keyed.enqueue_extract.calls == [doc.id] and keyed.enqueue.calls == []


async def test_extract_is_refused_without_a_key_or_without_text(
    api: Api, keyed: Api, session: AsyncSession
) -> None:
    with_text = await document(session, DocumentStatus.FAILED, "extraction_failed", text="x")
    blank = await document(session, DocumentStatus.FAILED, "ocr_failed", text="")

    disabled = await api.client.post(url(with_text.id), json={"from_stage": "extract"})
    no_text = await keyed.client.post(url(blank.id), json={"from_stage": "extract"})

    assert disabled.status_code == 409
    assert disabled.json()["detail"] == {"reason": "extraction_disabled"}
    assert no_text.status_code == 409 and no_text.json()["detail"] == {"reason": "no_text"}


async def test_a_running_document_is_refused(api: Api, session: AsyncSession) -> None:
    doc = await document(session, DocumentStatus.PROCESSING)

    response = await api.client.post(url(doc.id))

    assert response.status_code == 409
    assert response.json()["detail"] == {"reason": "already_queued"}
    assert api.enqueue.calls == []


async def test_a_broker_error_is_503_and_leaves_the_document_failed(
    api: Api, session: AsyncSession
) -> None:
    api.enqueue.fail = True
    doc = await document(session, DocumentStatus.FAILED, "ingest_failed")

    response = await api.client.post(url(doc.id))

    assert response.status_code == 503
    assert response.json()["detail"] == {"reason": "queue_unavailable"}
    detail = (await api.client.get(f"/api/v1/documents/{doc.id}")).json()
    assert (detail["status"], detail["error_code"]) == ("FAILED", "queue_unavailable")


async def test_unknown_document_and_bad_stage(api: Api, session: AsyncSession) -> None:
    doc = await document(session, DocumentStatus.FAILED)

    assert (await api.client.post(url(uuid.uuid4()))).status_code == 404
    assert (await api.client.post(url(doc.id), json={"from_stage": "nope"})).status_code == 422
    assert (await api.client.post("/api/v1/documents/not-a-uuid/reprocess")).status_code == 422


async def test_retry_failed_queues_each_document_from_the_stage_that_failed(
    keyed: Api, session: AsyncSession
) -> None:
    broken_model = await document(session, DocumentStatus.FAILED, "extraction_failed", text="x")
    broken_file = await document(session, DocumentStatus.FAILED, "pdf_corrupt")
    await document(session, DocumentStatus.COMPLETED)

    response = await keyed.client.post("/api/v1/jobs/retry-failed")

    assert response.status_code == 200
    assert response.json() == {
        "queued": [str(broken_model.id), str(broken_file.id)],
        "not_queued": 0,
    }
    assert keyed.enqueue_extract.calls == [broken_model.id]
    assert keyed.enqueue.calls == [broken_file.id]


async def test_retry_failed_honours_limit_and_validates_it(api: Api, session: AsyncSession) -> None:
    failed = [await document(session, DocumentStatus.FAILED, "ingest_failed") for _ in range(3)]

    limited = await api.client.post("/api/v1/jobs/retry-failed?limit=2")
    too_big = await api.client.post("/api/v1/jobs/retry-failed?limit=5000")
    empty = await api.client.post("/api/v1/jobs/retry-failed")

    assert limited.json()["queued"] == [str(failed[0].id), str(failed[1].id)]
    assert too_big.status_code == 422
    assert empty.json() == {"queued": [str(failed[2].id)], "not_queued": 0}  # the one left over
