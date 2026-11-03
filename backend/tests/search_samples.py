"""Helpers that put indexed documents into the test database."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, DocumentStatus, Page
from app.services.indexing import embed_missing_chunks, index_chunks
from tests.fake_embedder import FakeEmbedder
from tests.helpers import make_document


async def indexed(
    session: AsyncSession,
    *pages: str,
    embedded: bool = True,
    status: str = DocumentStatus.COMPLETED,
    name: str = "doc.pdf",
) -> Document:
    """A document whose pages are indexed (and embedded unless told otherwise)."""
    document = make_document(status=status, filename=name)
    session.add(document)
    await session.commit()
    session.add_all(
        Page(document_id=document.id, page_no=n, text=text, method="native")
        for n, text in enumerate(pages, start=1)
    )
    await session.commit()
    await index_chunks(session, document.id)
    await session.commit()
    if embedded:
        await embed_missing_chunks(session, document.id, FakeEmbedder())
    return document
