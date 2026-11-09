from collections.abc import AsyncIterator

import pytest

from app.core.config import Settings
from tests.helpers import Api, running_api

KEY = "test-key-123"
URL = "/api/v1/documents"
UNKNOWN = f"{URL}/00000000-0000-0000-0000-000000000000"


@pytest.fixture
async def secured(db: str, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Api]:
    monkeypatch.setenv("API_KEY", KEY)
    async with running_api(Settings()) as running:
        yield running


async def test_the_correct_key_is_accepted(secured: Api) -> None:
    response = await secured.client.get(UNKNOWN, headers={"X-API-Key": KEY})

    assert response.status_code == 404  # past the key check, then "no such document"


async def test_a_missing_or_wrong_key_is_unauthorized(secured: Api) -> None:
    for headers in ({}, {"X-API-Key": "wrong"}, {"X-API-Key": ""}):
        response = await secured.client.get(UNKNOWN, headers=headers)

        assert response.status_code == 401
        assert response.json() == {"detail": "Invalid or missing API key"}


async def test_every_versioned_route_is_protected(secured: Api) -> None:
    files = [("files", ("a.pdf", b"%PDF-1.4"))]

    assert (await secured.client.post(URL, files=files)).status_code == 401
    assert (await secured.client.post("/api/v1/cross-verify", json={})).status_code == 401
    assert (await secured.client.post("/api/v1/chat", json={"question": "hi"})).status_code == 401
    assert (await secured.client.get(f"{UNKNOWN}/result")).status_code == 401
    assert (await secured.client.get("/api/v1/chat/sessions")).status_code == 401
    assert secured.enqueue.calls == []  # nothing was stored or queued


async def test_health_endpoints_stay_open(secured: Api) -> None:
    assert (await secured.client.get("/healthz")).status_code == 200


async def test_a_browser_preflight_is_answered_without_the_key(secured: Api) -> None:
    response = await secured.client.options(
        URL,
        headers={
            "Origin": secured.settings.web_origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "x-api-key",
        },
    )

    assert response.status_code == 200
    assert "x-api-key" in response.headers["access-control-allow-headers"].lower()


async def test_without_a_configured_key_requests_need_none(api: Api) -> None:
    assert (await api.client.get(UNKNOWN)).status_code == 404
