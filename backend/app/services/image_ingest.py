from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document
from app.pipeline.image import ImageReader
from app.services.pages import ingest_pages
from app.services.storage import Storage


async def ingest_image(session: AsyncSession, storage: Storage, document: Document) -> None:
    # Every frame is saved as a `scanned` page: it has a picture and no text yet, so OCR reads it.
    await ingest_pages(session, storage, document, ImageReader)
