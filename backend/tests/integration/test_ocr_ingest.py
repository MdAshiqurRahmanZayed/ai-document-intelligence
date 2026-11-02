from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, Page
from app.services.ocr_ingest import ocr_pages
from tests import image_samples as samples
from tests.fakes import FakeStorage
from tests.helpers import make_document


async def document_with_pages(
    session: AsyncSession, storage: FakeStorage, pages: list[Page], images: dict[int, bytes]
) -> Document:
    document = make_document(source_type="image", mime="image/png")
    session.add(document)
    await session.commit()
    for page in pages:
        page.document_id = document.id
        if page.page_no in images:
            page.image_key = f"pages/{document.id}/{page.page_no}.png"
            storage.objects[page.image_key] = (images[page.page_no], "image/png")
        session.add(page)
    await session.commit()
    return document


async def pages_of(session: AsyncSession, document: Document) -> list[Page]:
    result = await session.scalars(
        select(Page)
        .where(Page.document_id == document.id)
        .order_by(Page.page_no)
        .execution_options(populate_existing=True)
    )
    return list(result)


async def test_scanned_pages_are_read_and_native_pages_are_left_alone(
    session: AsyncSession,
) -> None:
    storage = FakeStorage()
    document = await document_with_pages(
        session,
        storage,
        [Page(page_no=1, method="native", text="embedded"), Page(page_no=2, method="scanned")],
        {2: samples.encode(samples.text_image())},
    )

    await ocr_pages(session, storage, document)

    native, scanned = await pages_of(session, document)
    assert (native.text, native.method, native.ocr_confidence) == ("embedded", "native", None)
    assert scanned.method == "ocr" and "INVOICE" in (scanned.text or "")
    assert scanned.ocr_confidence is not None and scanned.ocr_confidence > 0.8


async def test_rerun_reads_only_the_pages_still_scanned(session: AsyncSession) -> None:
    storage = FakeStorage()
    document = await document_with_pages(
        session,
        storage,
        [
            Page(page_no=1, method="ocr", text="already done", ocr_confidence=0.5),
            Page(page_no=2, method="scanned"),
        ],
        {1: samples.encode(samples.text_image()), 2: samples.encode(samples.text_image())},
    )

    await ocr_pages(session, storage, document)

    done, fresh = await pages_of(session, document)
    assert (done.text, done.ocr_confidence) == ("already done", 0.5)
    assert "INVOICE" in (fresh.text or "")


async def test_blank_page_is_saved_empty_without_failing(session: AsyncSession) -> None:
    storage = FakeStorage()
    document = await document_with_pages(
        session,
        storage,
        [Page(page_no=1, method="scanned")],
        {1: samples.encode(samples.blank_image())},
    )

    await ocr_pages(session, storage, document)

    (page,) = await pages_of(session, document)
    assert (page.text, page.method, page.ocr_confidence) == ("", "ocr", None)
