from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, Page
from app.services.spreadsheet_ingest import ingest_spreadsheet
from tests import spreadsheet_samples as samples
from tests.fakes import FakeStorage
from tests.helpers import make_document

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


async def stored(
    session: AsyncSession, storage: FakeStorage, content: bytes, mime: str, filename: str
) -> Document:
    document = make_document(source_type="spreadsheet", mime=mime, filename=filename)
    storage.objects[document.storage_key] = (content, mime)
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


async def test_workbook_saves_one_native_page_per_sheet_with_data(session: AsyncSession) -> None:
    storage = FakeStorage()
    document = await stored(session, storage, samples.multi_sheet_xlsx(), XLSX, "inv.xlsx")

    await ingest_spreadsheet(session, storage, document)

    pages = await pages_of(session, document)
    assert document.page_count == len(pages) == 2  # the empty sheet is skipped
    assert [(p.page_no, p.method, p.image_key, p.ocr_confidence) for p in pages] == [
        (1, "native", None, None),
        (2, "native", None, None),
    ]
    assert (pages[0].text or "").startswith("Sheet: Invoices\n")
    assert not any(key.startswith("pages/") for key in storage.objects)  # no images stored


async def test_rerun_leaves_one_row_per_page_with_the_same_text(session: AsyncSession) -> None:
    storage = FakeStorage()
    document = await stored(session, storage, samples.big_xlsx(250), XLSX, "big.xlsx")

    await ingest_spreadsheet(session, storage, document)
    first = [p.text for p in await pages_of(session, document)]
    await ingest_spreadsheet(session, storage, document)
    second = [p.text for p in await pages_of(session, document)]

    assert len(first) == 3
    assert first == second


async def test_csv_document_is_named_after_its_file(session: AsyncSession) -> None:
    storage = FakeStorage()
    document = await stored(
        session, storage, samples.csv_semicolon_latin1(), "text/csv", "lieferungen.csv"
    )

    await ingest_spreadsheet(session, storage, document)

    (page,) = await pages_of(session, document)
    assert page.text == "Sheet: lieferungen\nLieferant | Betrag\nMüller GmbH | 120,50"
