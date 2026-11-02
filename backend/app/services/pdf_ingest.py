import asyncio
import io
import tempfile
from collections.abc import Generator
from itertools import islice
from pathlib import Path

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, Page
from app.pipeline.pdf import PageContent, PdfReader
from app.services.storage import Storage

# Pages saved per commit: progress survives a crash without a commit per page.
BATCH_SIZE = 25


async def ingest_pdf(session: AsyncSession, storage: Storage, document: Document) -> None:
    """Save one page row per PDF page; scanned pages also get an image for the OCR step.

    Safe to run again: rows are upserted by (document_id, page_no).
    """
    # PDFium needs a real file. Streaming to disk keeps memory flat for any PDF size.
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "document.pdf"
        with path.open("wb") as file:
            await storage.download(document.storage_key, file)

        reader = PdfReader(path)
        document.page_count = await asyncio.to_thread(reader.page_count)
        await session.commit()  # lets progress be shown while the pages are still being read

        pages = reader.pages()
        try:
            while batch := await asyncio.to_thread(_next_batch, pages):
                await _save_batch(session, storage, document, batch)
        finally:
            pages.close()


def _next_batch(pages: Generator[PageContent]) -> list[PageContent]:
    # PDFium is blocking and CPU-bound, so reading runs in a thread, off the event loop.
    return list(islice(pages, BATCH_SIZE))


async def _save_batch(
    session: AsyncSession, storage: Storage, document: Document, batch: list[PageContent]
) -> None:
    rows = []
    for page in batch:
        image_key = None
        if page.image is not None:
            image_key = f"pages/{document.id}/{page.page_no}.png"
            # Image first: if this fails no row exists yet, so nothing points at a missing file.
            await storage.put(image_key, io.BytesIO(page.image), "image/png")
        rows.append(
            {
                "document_id": document.id,
                "page_no": page.page_no,
                "text": page.text,
                "method": "native" if page.image is None else "scanned",
                "image_key": image_key,
            }
        )

    statement = insert(Page).values(rows)
    await session.execute(
        statement.on_conflict_do_update(
            constraint="uq_pages_document_id_page_no",
            set_={c: statement.excluded[c] for c in ("text", "method", "image_key")},
        )
    )
    await session.commit()
