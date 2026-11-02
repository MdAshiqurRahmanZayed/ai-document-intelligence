import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, Page
from app.services import pdf_ingest
from app.services.pdf_ingest import ingest_pdf
from tests import pdf_samples as samples
from tests.fakes import FakeStorage
from tests.helpers import make_document


async def stored(session: AsyncSession, storage: FakeStorage, content: bytes) -> Document:
    document = make_document()
    storage.objects[document.storage_key] = (content, "application/pdf")
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


async def test_text_pdf_saves_one_native_row_per_page(session: AsyncSession) -> None:
    storage = FakeStorage()
    document = await stored(session, storage, samples.text_pdf(3))

    await ingest_pdf(session, storage, document)

    pages = await pages_of(session, document)
    assert document.page_count == 3
    assert [(p.page_no, p.method, p.image_key) for p in pages] == [
        (1, "native", None),
        (2, "native", None),
        (3, "native", None),
    ]
    assert all(p.text for p in pages)


async def test_images_are_stored_only_for_scanned_pages(session: AsyncSession) -> None:
    storage = FakeStorage()
    document = await stored(session, storage, samples.mixed_pdf())

    await ingest_pdf(session, storage, document)

    pages = await pages_of(session, document)
    key = f"pages/{document.id}/2.png"
    assert [p.method for p in pages] == ["native", "scanned", "native"]
    assert [p.image_key for p in pages] == [None, key, None]
    assert pages[1].text is None
    assert [k for k in storage.objects if k.startswith("pages/")] == [key]
    assert storage.objects[key][1] == "image/png"


async def test_rerun_updates_rows_in_place(session: AsyncSession) -> None:
    storage = FakeStorage()
    document = await stored(session, storage, samples.text_pdf(3))

    await ingest_pdf(session, storage, document)
    await ingest_pdf(session, storage, document)

    assert len(await pages_of(session, document)) == 3


async def test_failed_image_upload_leaves_no_row_pointing_at_it(session: AsyncSession) -> None:
    storage = FakeStorage()
    document = await stored(session, storage, samples.scanned_pdf())
    storage.fail_put = True  # set after seeding the original file

    with pytest.raises(RuntimeError):
        await ingest_pdf(session, storage, document)

    assert await pages_of(session, document) == []


async def test_pages_are_committed_in_batches(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(pdf_ingest, "BATCH_SIZE", 2)
    storage = FakeStorage()
    document = await stored(session, storage, samples.text_pdf(5))
    commits = 0
    original = session.commit

    async def counting_commit() -> None:
        nonlocal commits
        commits += 1
        await original()

    monkeypatch.setattr(session, "commit", counting_commit)

    await ingest_pdf(session, storage, document)

    assert commits == 1 + 3  # page_count, then batches of 2, 2 and 1
    assert len(await pages_of(session, document)) == 5
