import asyncio
import time
from collections.abc import AsyncIterator, Callable

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.main import create_app
from app.services.readiness import Check

MakeClient = Callable[[dict[str, Check]], AsyncClient]


async def ok() -> None:
    return None


async def boom() -> None:
    raise RuntimeError("postgresql://user:hunter2@db.internal/app refused")


async def hang() -> None:
    await asyncio.sleep(30)


@pytest.fixture
async def make_client(valid_env: pytest.MonkeyPatch) -> AsyncIterator[MakeClient]:
    clients: list[AsyncClient] = []

    def make(checks: dict[str, Check]) -> AsyncClient:
        app = create_app(Settings())
        app.state.checks = checks
        client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
        clients.append(client)
        return client

    yield make
    for client in clients:
        await client.aclose()


async def test_healthz_ok(make_client: MakeClient) -> None:
    async with make_client({"database": ok}) as client:
        response = await client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_healthz_ignores_failing_dependencies(make_client: MakeClient) -> None:
    async with make_client({"database": boom, "redis": boom, "storage": boom}) as client:
        response = await client.get("/healthz")
    assert response.status_code == 200


async def test_readyz_all_ok(make_client: MakeClient) -> None:
    async with make_client({"database": ok, "redis": ok, "storage": ok}) as client:
        response = await client.get("/readyz")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "checks": {"database": "ok", "redis": "ok", "storage": "ok"},
    }


async def test_readyz_one_failing(make_client: MakeClient) -> None:
    async with make_client({"database": ok, "redis": boom, "storage": ok}) as client:
        response = await client.get("/readyz")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "error"
    assert body["checks"] == {"database": "ok", "redis": "error", "storage": "ok"}


async def test_readyz_hanging_check_times_out(
    make_client: MakeClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("READINESS_TIMEOUT_SECONDS", "0.2")
    async with make_client({"database": ok, "redis": hang}) as client:
        start = time.perf_counter()
        response = await client.get("/readyz")
        elapsed = time.perf_counter() - start
    assert elapsed < 1.5
    assert response.status_code == 503
    assert response.json()["checks"] == {"database": "ok", "redis": "error"}


async def test_readyz_hides_internals_but_logs_them(
    make_client: MakeClient,
    capsys: pytest.CaptureFixture[str],
) -> None:
    async with make_client({"database": boom}) as client:
        response = await client.get("/readyz")
    assert "hunter2" not in response.text
    assert "RuntimeError" not in response.text
    assert "readiness_check_failed" in capsys.readouterr().out
