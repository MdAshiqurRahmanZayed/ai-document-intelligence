import asyncio
import uuid
from collections.abc import Awaitable, Callable, Coroutine
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import Settings
from app.db.models import Document
from tests.fakes import FakeStorage, RecordingEnqueue


def run_sync[T](coro: Coroutine[Any, Any, T]) -> T:
    # A private loop: asyncio.run() would reset the current loop that pytest-asyncio relies on.
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def with_session[T](url: str, fn: Callable[[AsyncSession], Awaitable[T]]) -> T:
    """Run `fn` against the test database from synchronous test code."""

    async def go() -> T:
        engine = create_async_engine(url, poolclass=NullPool)
        try:
            async with async_sessionmaker(engine, expire_on_commit=False)() as session:
                return await fn(session)
        finally:
            await engine.dispose()

    return run_sync(go())


def make_document(**overrides: Any) -> Document:
    document_id = overrides.pop("id", uuid.uuid4())
    fields: dict[str, Any] = {
        "id": document_id,
        "filename": "invoice.pdf",
        "mime": "application/pdf",
        "size": 10,
        "sha256": uuid.uuid4().hex + uuid.uuid4().hex,  # 64 hex chars, unique per call
        "storage_key": f"raw/{document_id}/original.pdf",
        "source_type": "pdf",
    }
    fields.update(overrides)
    return Document(**fields)


@dataclass
class Api:
    """A running app with in-memory storage and queue, and a client that talks to it."""

    client: AsyncClient
    storage: FakeStorage
    enqueue: RecordingEnqueue
    settings: Settings
    app: FastAPI
