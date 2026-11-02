import uuid
from collections.abc import Callable, Iterator
from typing import Any

import pytest
from celery import Task
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, DocumentStatus, ProcessingEvent
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


def queued_document(db: str) -> uuid.UUID:
    document = make_document(status=DocumentStatus.QUEUED)

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

    async def flaky(document: Document) -> None:
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
    async def always_fails(document: Document) -> None:
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
