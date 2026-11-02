from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document
from app.pipeline.spreadsheet import SpreadsheetReader
from app.services.pages import ingest_pages
from app.services.storage import Storage


async def ingest_spreadsheet(session: AsyncSession, storage: Storage, document: Document) -> None:
    # Pages hold the table text and no image, so they are saved as `native` and need no OCR.
    # The format comes from the detected mime, never from the client's filename.
    await ingest_pages(
        session,
        storage,
        document,
        lambda path: SpreadsheetReader(path, document.mime, Path(document.filename).stem),
    )
