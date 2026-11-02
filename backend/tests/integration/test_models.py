import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, DocumentStatus, Page, ProcessingEvent
from tests.helpers import make_document


async def test_new_document_defaults(session: AsyncSession) -> None:
    document = make_document()
    session.add(document)
    await session.commit()
    await session.refresh(document)

    assert document.status == DocumentStatus.UPLOADED
    assert document.created_at is not None


async def test_sha256_must_be_unique(session: AsyncSession) -> None:
    session.add(make_document(sha256="a" * 64))
    session.add(make_document(sha256="a" * 64))
    with pytest.raises(IntegrityError):
        await session.commit()


async def test_page_number_is_unique_per_document(session: AsyncSession) -> None:
    document = make_document()
    session.add(document)
    await session.commit()

    session.add_all(
        [Page(document_id=document.id, page_no=1), Page(document_id=document.id, page_no=1)]
    )
    with pytest.raises(IntegrityError):
        await session.commit()


async def test_deleting_a_document_removes_its_pages_and_events(session: AsyncSession) -> None:
    document = make_document()
    session.add(document)
    await session.commit()
    session.add(Page(document_id=document.id, page_no=1))
    session.add(
        ProcessingEvent(document_id=document.id, stage="ingest", status="started", attempt=1)
    )
    await session.commit()

    await session.execute(delete(Document))
    await session.commit()

    for model in (Page, ProcessingEvent):
        assert await session.scalar(select(func.count()).select_from(model)) == 0
