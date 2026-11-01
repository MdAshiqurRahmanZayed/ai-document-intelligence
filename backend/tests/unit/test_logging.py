import json

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.logging import RequestLogMiddleware, configure_logging


async def test_request_emits_json_log_line(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("INFO", "test-service")
    app = FastAPI()
    app.add_middleware(RequestLogMiddleware)

    @app.get("/ping")
    async def ping() -> dict[str, str]:
        return {}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/ping")

    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.strip()]
    entry = next(line for line in lines if line["message"] == "request")
    assert {"timestamp", "level", "service", "message"} <= entry.keys()
    assert entry["service"] == "test-service"
    assert entry["status"] == 200
    assert entry["request_id"] == response.headers["x-request-id"]
