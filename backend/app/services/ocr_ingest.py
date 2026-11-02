import asyncio
import io

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, Page
from app.pipeline.ocr import OcrEngine, OcrResult
from app.services.storage import Storage

# Pages read per commit: OCR is slow, so progress is saved often enough to resume cheaply.
BATCH_SIZE = 10


async def has_scanned_pages(session: AsyncSession, document: Document) -> bool:
    return bool(
        await session.scalar(
            select(exists().where(Page.document_id == document.id, Page.method == "scanned"))
        )
    )


async def ocr_pages(
    session: AsyncSession, storage: Storage, document: Document, concurrency: int = 4
) -> None:
    """Read every page still marked `scanned`, up to `concurrency` pages at a time.

    Safe to run again: a finished page is no longer `scanned`, so a crash or redelivery only
    redoes the pages that were not saved yet.
    """
    engine = OcrEngine()
    limit = asyncio.Semaphore(concurrency)

    async def read(page: Page) -> OcrResult:
        assert page.image_key is not None  # every scanned page is saved with its image
        # The download sits inside the limit too, so only `concurrency` images are in memory.
        async with limit:
            png = io.BytesIO()
            await storage.download(page.image_key, png)
            # Tesseract is blocking and CPU-bound, so it runs in a thread, off the event loop.
            return await asyncio.to_thread(engine.read, png.getvalue())

    while True:
        pages = (
            await session.scalars(
                select(Page)
                .where(Page.document_id == document.id, Page.method == "scanned")
                .order_by(Page.page_no)
                .limit(BATCH_SIZE)
            )
        ).all()
        if not pages:
            return
        results = await asyncio.gather(*(read(page) for page in pages))
        # Database writes stay sequential: one session, one commit per batch.
        for page, result in zip(pages, results, strict=True):
            page.text, page.method, page.ocr_confidence = result.text, "ocr", result.confidence
        await session.commit()
