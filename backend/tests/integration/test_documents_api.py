import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.core.config import Settings
from app.db.models import Document
from app.main import create_app
from tests import samples
from tests.fakes import FakeStorage, RecordingEnqueue

URL = "/api/v1/documents"


@dataclass
class Api:
    client: AsyncClient
    storage: FakeStorage
    enqueue: RecordingEnqueue
    settings: Settings
    app: FastAPI


@pytest.fixture
async def api(db: str) -> AsyncIterator[Api]:
    settings = Settings()
    app = create_app(settings)
    storage, enqueue = FakeStorage(), RecordingEnqueue()
    app.state.storage = storage
    app.state.enqueue = enqueue
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield Api(client, storage, enqueue, settings, app)
    await app.state.engine.dispose()


def part(name: str, data: bytes) -> tuple[str, tuple[str, bytes]]:
    return ("files", (name, data))


async def test_two_valid_files_are_accepted(api: Api) -> None:
    response = await api.client.post(
        URL, files=[part("a.pdf", samples.pdf()), part("b.csv", samples.CSV)]
    )

    assert response.status_code == 202
    results = response.json()["results"]
    assert [r["status"] for r in results] == ["accepted", "accepted"]
    assert all(r["document_id"] for r in results)
    assert len(api.enqueue.calls) == 2


async def test_mixed_outcomes_still_store_the_valid_file(api: Api) -> None:
    response = await api.client.post(
        URL, files=[part("a.pdf", samples.pdf()), part("empty.pdf", b"")]
    )

    results = response.json()["results"]
    assert (results[0]["status"], results[1]["status"]) == ("accepted", "rejected")
    assert results[1]["reason"] == "empty_file"
    assert len(api.storage.objects) == 1


async def test_request_without_files_is_422(api: Api) -> None:
    assert (await api.client.post(URL)).status_code == 422


async def test_same_bytes_twice_in_one_request(api: Api) -> None:
    response = await api.client.post(
        URL, files=[part("a.pdf", samples.pdf()), part("b.pdf", samples.pdf())]
    )

    first, second = response.json()["results"]
    assert (first["status"], second["status"]) == ("accepted", "duplicate")
    assert second["document_id"] == first["document_id"]
    assert len(api.enqueue.calls) == 1


async def test_oversized_file_is_rejected(api: Api) -> None:
    api.settings.max_upload_mb = 1
    data = samples.pdf("z" * (1024 * 1024))
    response = await api.client.post(URL, files=[part("big.pdf", data)])

    result = response.json()["results"][0]
    assert (result["status"], result["reason"]) == ("rejected", "file_too_large")
    assert api.storage.objects == {}


async def test_hostile_filename_never_reaches_the_storage_key(api: Api) -> None:
    await api.client.post(URL, files=[part("../../etc/passwd", samples.pdf())])

    (key,) = api.storage.objects
    assert key.startswith("raw/") and key.endswith("/original.pdf")
    assert "passwd" not in key


async def test_queue_failure_is_reported_and_visible_in_status(api: Api) -> None:
    api.enqueue.fail = True
    result = (await api.client.post(URL, files=[part("a.pdf", samples.pdf())])).json()["results"][0]

    assert (result["status"], result["reason"]) == ("rejected", "queue_unavailable")
    details = (await api.client.get(f"{URL}/{result['document_id']}")).json()
    assert (details["status"], details["error_code"]) == ("FAILED", "queue_unavailable")


async def test_storage_failure_creates_no_document(api: Api) -> None:
    api.storage.fail_put = True
    result = (await api.client.post(URL, files=[part("a.pdf", samples.pdf())])).json()["results"][0]

    assert (result["status"], result["reason"]) == ("rejected", "storage_error")

    async with api.app.state.session_factory() as session:
        count = await session.scalar(select(func.count()).select_from(Document))
    assert count == 0


async def test_document_details_after_upload(api: Api) -> None:
    result = (await api.client.post(URL, files=[part("invoice.pdf", samples.pdf())])).json()[
        "results"
    ][0]
    response = await api.client.get(f"{URL}/{result['document_id']}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == result["document_id"]
    assert body["filename"] == "invoice.pdf"
    assert body["mime"] == "application/pdf"
    assert body["status"] == "QUEUED"
    assert body["events"] == []
    assert body["created_at"]


async def test_unknown_document_is_404(api: Api) -> None:
    assert (await api.client.get(f"{URL}/{uuid.uuid4()}")).status_code == 404


async def test_malformed_id_is_422(api: Api) -> None:
    assert (await api.client.get(f"{URL}/not-a-uuid")).status_code == 422


async def test_reupload_after_a_queue_failure_retries_the_document(api: Api) -> None:
    api.enqueue.fail = True
    failed = (await api.client.post(URL, files=[part("a.pdf", samples.pdf())])).json()["results"][0]
    assert failed["reason"] == "queue_unavailable"

    api.enqueue.fail = False
    retry = (await api.client.post(URL, files=[part("a.pdf", samples.pdf())])).json()["results"][0]

    assert retry["status"] == "accepted"
    assert retry["document_id"] == failed["document_id"]
    details = (await api.client.get(f"{URL}/{retry['document_id']}")).json()
    assert (details["status"], details["error_code"]) == ("QUEUED", None)
