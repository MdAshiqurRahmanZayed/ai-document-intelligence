"""Large-document benchmarks. Slow, so they only run with `make bench` (pytest -m slow -s).

They print their measurements; the numbers worth keeping go into docs/performance.md.
"""

import resource
import sys
import time

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, Page
from app.services.ocr_ingest import ocr_pages
from app.services.pdf_ingest import ingest_pdf
from tests import image_samples as images
from tests import pdf_samples as pdfs
from tests.fakes import FakeStorage
from tests.helpers import make_document

pytestmark = pytest.mark.slow

# Peak memory may grow by at most this much when the document is ten times longer.
# Measured growth was 4 MB (docs/performance.md); the bound leaves room for noise only.
MAX_MEMORY_GROWTH_MB = 50
SCANNED_PAGES = 40


def peak_memory_mb() -> float:
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak / (1024 * 1024 if sys.platform == "darwin" else 1024)  # bytes on macOS, KB on Linux


async def stored_pdf(session: AsyncSession, storage: FakeStorage, content: bytes) -> Document:
    document = make_document(source_type="pdf")
    storage.objects[document.storage_key] = (content, document.mime)
    session.add(document)
    await session.commit()
    return document


async def page_count(session: AsyncSession, document: Document) -> int:
    count = await session.scalar(select(func.count()).where(Page.document_id == document.id))
    return count or 0


async def test_memory_does_not_grow_with_page_count(session: AsyncSession) -> None:
    storage = FakeStorage()
    # Both files are built first so building them is not counted as ingest memory.
    hundred = await stored_pdf(session, storage, pdfs.text_pdf(100))
    thousand = await stored_pdf(session, storage, pdfs.text_pdf(1000))

    start = time.perf_counter()
    await ingest_pdf(session, storage, hundred)
    seconds_100 = time.perf_counter() - start
    after_100 = peak_memory_mb()

    start = time.perf_counter()
    await ingest_pdf(session, storage, thousand)
    seconds_1000 = time.perf_counter() - start
    after_1000 = peak_memory_mb()

    print(
        f"\n[bench] 100 pages: {seconds_100:.1f}s, 1000 pages: {seconds_1000:.1f}s "
        f"({seconds_1000 / 10:.1f}s per 100 pages)"
        f"\n[bench] peak memory after 100 pages: {after_100:.0f} MB, "
        f"after 1000 pages: {after_1000:.0f} MB (growth {after_1000 - after_100:.0f} MB)"
    )
    assert await page_count(session, hundred) == 100
    assert await page_count(session, thousand) == 1000
    assert after_1000 - after_100 < MAX_MEMORY_GROWTH_MB


async def scanned_document(session: AsyncSession, storage: FakeStorage) -> Document:
    document = make_document(source_type="image", mime="image/png")
    session.add(document)
    await session.commit()
    image = images.encode(images.text_image())
    for n in range(1, SCANNED_PAGES + 1):
        key = f"pages/{document.id}/{n}.png"
        storage.objects[key] = (image, "image/png")
        session.add(Page(document_id=document.id, page_no=n, method="scanned", image_key=key))
    await session.commit()
    return document


async def test_concurrent_ocr_gives_the_same_pages_faster(session: AsyncSession) -> None:
    storage = FakeStorage()
    timings: dict[int, float] = {}
    results: dict[int, list[tuple[str | None, str | None, float | None]]] = {}

    for limit in (1, 4):
        document = await scanned_document(session, storage)
        start = time.perf_counter()
        await ocr_pages(session, storage, document, concurrency=limit)
        timings[limit] = time.perf_counter() - start
        pages = await session.scalars(
            select(Page)
            .where(Page.document_id == document.id)
            .order_by(Page.page_no)
            .execution_options(populate_existing=True)
        )
        results[limit] = [(p.text, p.method, p.ocr_confidence) for p in pages]

    print(
        f"\n[bench] OCR of {SCANNED_PAGES} pages: {timings[1]:.1f}s with 1 at a time, "
        f"{timings[4]:.1f}s with 4 at a time (speedup {timings[1] / timings[4]:.1f}x)"
    )
    assert results[1] == results[4]
    assert {method for _, method, _ in results[1]} == {"ocr"}
