import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, Page
from app.services.image_ingest import ingest_image
from tests import image_samples as samples
from tests.fakes import FakeStorage
from tests.helpers import make_document


async def stored(session: AsyncSession, storage: FakeStorage, content: bytes) -> Document:
    document = make_document(source_type="image", mime="image/png")
    storage.objects[document.storage_key] = (content, document.mime)
    session.add(document)
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


async def test_single_image_becomes_one_scanned_page(session: AsyncSession) -> None:
    storage = FakeStorage()
    document = await stored(session, storage, samples.encode(samples.text_image()))

    await ingest_image(session, storage, document)

    (page,) = await pages_of(session, document)
    key = f"pages/{document.id}/1.png"
    assert document.page_count == 1
    assert (page.page_no, page.method, page.text, page.image_key) == (1, "scanned", None, key)
    assert storage.objects[key][1] == "image/png"


async def test_multi_frame_tiff_becomes_one_page_per_frame(session: AsyncSession) -> None:
    storage = FakeStorage()
    document = await stored(session, storage, samples.tiff([samples.text_image()] * 3))

    await ingest_image(session, storage, document)

    pages = await pages_of(session, document)
    assert document.page_count == 3
    assert [p.image_key for p in pages] == [f"pages/{document.id}/{n}.png" for n in (1, 2, 3)]
    assert len([k for k in storage.objects if k.startswith("pages/")]) == 3


async def test_rerun_updates_rows_in_place(session: AsyncSession) -> None:
    storage = FakeStorage()
    document = await stored(session, storage, samples.tiff([samples.text_image()] * 2))

    await ingest_image(session, storage, document)
    await ingest_image(session, storage, document)

    assert len(await pages_of(session, document)) == 2


async def test_failed_upload_leaves_no_row_pointing_at_it(session: AsyncSession) -> None:
    storage = FakeStorage()
    document = await stored(session, storage, samples.encode(samples.text_image()))
    storage.fail_put = True  # set after seeding the original file

    with pytest.raises(RuntimeError):
        await ingest_image(session, storage, document)

    assert await pages_of(session, document) == []
