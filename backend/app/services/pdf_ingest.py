from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document
from app.pipeline.pdf import PdfReader
from app.services.pages import ingest_pages
from app.services.storage import Storage


async def ingest_pdf(session: AsyncSession, storage: Storage, document: Document) -> None:
    await ingest_pages(session, storage, document, PdfReader)
