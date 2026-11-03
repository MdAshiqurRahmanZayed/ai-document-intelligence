from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, DocumentStatus
from app.services.listing import DocumentFilters, InvalidCursor, list_documents
from tests.listing_samples import add_document, add_invoice


async def ids(session: AsyncSession, filters: DocumentFilters, limit: int = 100) -> list[str]:
    page = await list_documents(session, filters, limit, None)
    return [row.document.filename for row in page.items]


async def named(
    session: AsyncSession, name: str, minutes: int = 0, status: str = DocumentStatus.COMPLETED
) -> Document:
    document = await add_document(session, minutes, status)
    document.filename = name
    await session.commit()
    return document


async def test_documents_come_newest_first_in_pages_without_repeats(session: AsyncSession) -> None:
    for n in range(25):
        await named(session, f"doc-{n:02d}", minutes=n)

    seen: list[str] = []
    sizes: list[int] = []
    cursor = None
    while True:
        page = await list_documents(session, DocumentFilters(), 10, cursor)
        sizes.append(len(page.items))
        seen += [row.document.filename for row in page.items]
        cursor = page.next_cursor
        if cursor is None:
            break

    assert sizes == [10, 10, 5]
    assert seen == [f"doc-{n:02d}" for n in range(24, -1, -1)]  # each once, newest first


async def test_an_exact_page_has_no_next_cursor(session: AsyncSession) -> None:
    for n in range(10):
        await add_document(session, n)

    page = await list_documents(session, DocumentFilters(), 10, None)

    assert len(page.items) == 10 and page.next_cursor is None


async def test_documents_created_at_the_same_moment_are_still_paged_exactly_once(
    session: AsyncSession,
) -> None:
    for _ in range(5):
        await add_document(session, minutes=0)  # identical created_at: the id breaks the tie

    first = await list_documents(session, DocumentFilters(), 2, None)
    second = await list_documents(session, DocumentFilters(), 2, first.next_cursor)
    third = await list_documents(session, DocumentFilters(), 2, second.next_cursor)

    seen = [r.document.id for p in (first, second, third) for r in p.items]
    assert len(seen) == 5 and len(set(seen)) == 5 and third.next_cursor is None


async def test_a_malformed_cursor_is_rejected(session: AsyncSession) -> None:
    with pytest.raises(InvalidCursor):
        await list_documents(session, DocumentFilters(), 10, "garbage")


async def test_the_invoice_summary_shows_only_current_versions_in_order(
    session: AsyncSession,
) -> None:
    document = await add_document(session)
    await add_invoice(session, document, index=1, number="INV-B", total="2.00")
    await add_invoice(session, document, index=0, number="INV-A-OLD", version=1, current=False)
    await add_invoice(session, document, index=0, number="INV-A", version=2)

    (row,) = (await list_documents(session, DocumentFilters(), 10, None)).items

    assert [(i.invoice_index, i.invoice_number) for i in row.invoices] == [
        (0, "INV-A"),
        (1, "INV-B"),
    ]
    assert row.invoices[0].supplier_name == "Acme Industries Ltd."
    assert row.invoices[1].total == Decimal("2.00")


async def test_a_document_without_invoices_has_an_empty_list(session: AsyncSession) -> None:
    await add_document(session)

    (row,) = (await list_documents(session, DocumentFilters(), 10, None)).items

    assert row.invoices == []


async def test_filter_by_status(session: AsyncSession) -> None:
    await named(session, "done", status=DocumentStatus.COMPLETED)
    await named(session, "review", minutes=1, status=DocumentStatus.NEEDS_REVIEW)

    assert await ids(session, DocumentFilters(status="NEEDS_REVIEW")) == ["review"]


@pytest.mark.parametrize("query", ["acme", "ACME", "Acme Industries", "industries ltd", "acme."])
async def test_filter_by_supplier_ignores_case_punctuation_and_company_form(
    session: AsyncSession, query: str
) -> None:
    document = await named(session, "match")
    await add_invoice(session, document, supplier="Acme Industries Ltd.")
    other = await named(session, "other", minutes=1)
    await add_invoice(session, other, supplier="Globex Corporation")

    assert await ids(session, DocumentFilters(supplier=query)) == ["match"]


async def test_an_underscore_in_the_supplier_filter_is_not_a_wildcard(
    session: AsyncSession,
) -> None:
    document = await named(session, "doc")
    await add_invoice(session, document, supplier="Acme Ltd")

    # In SQL LIKE an underscore matches any one character, so unescaped "ac_e" would find "acme".
    assert await ids(session, DocumentFilters(supplier="ac_e")) == []
    assert await ids(session, DocumentFilters(supplier="acme")) == ["doc"]


async def test_a_supplier_filter_without_letters_or_digits_is_ignored(
    session: AsyncSession,
) -> None:
    document = await named(session, "doc")
    await add_invoice(session, document, supplier="Acme Ltd")

    assert await ids(session, DocumentFilters(supplier="%")) == ["doc"]


@pytest.mark.parametrize("query", ["INV-007", "inv 007", "inv007"])
async def test_filter_by_invoice_number_ignores_case_and_punctuation(
    session: AsyncSession, query: str
) -> None:
    document = await named(session, "match")
    await add_invoice(session, document, number="INV-007")
    other = await named(session, "other", minutes=1)
    await add_invoice(session, other, number="INV-0071")

    assert await ids(session, DocumentFilters(invoice_number=query)) == ["match"]


async def test_filter_by_date_range_amount_range_and_currency(session: AsyncSession) -> None:
    jan = await named(session, "jan-eur-50")
    await add_invoice(session, jan, on=date(2026, 1, 5), total="50.00", currency="EUR")
    mar = await named(session, "mar-usd-150", minutes=1)
    await add_invoice(session, mar, on=date(2026, 3, 1), total="150.00", currency="USD")

    assert await ids(session, DocumentFilters(date_from=date(2026, 2, 1))) == ["mar-usd-150"]
    assert await ids(session, DocumentFilters(date_to=date(2026, 1, 5))) == ["jan-eur-50"]
    assert await ids(session, DocumentFilters(amount_min=Decimal("100"))) == ["mar-usd-150"]
    assert await ids(session, DocumentFilters(amount_max=Decimal("50.00"))) == ["jan-eur-50"]
    assert await ids(session, DocumentFilters(currency="eur")) == ["jan-eur-50"]
    both = DocumentFilters(currency="USD", amount_min=Decimal("100"), amount_max=Decimal("200"))
    assert await ids(session, both) == ["mar-usd-150"]


async def test_one_invoice_must_satisfy_all_invoice_filters_together(
    session: AsyncSession,
) -> None:
    document = await named(session, "two-invoices")
    await add_invoice(session, document, index=0, on=date(2026, 1, 5), total="50.00")
    await add_invoice(session, document, index=1, on=date(2026, 3, 1), total="500.00")

    split = DocumentFilters(date_from=date(2026, 2, 1), amount_max=Decimal("100"))
    same = DocumentFilters(date_from=date(2026, 2, 1), amount_min=Decimal("100"))

    assert await ids(session, split) == []  # March is late enough, January is cheap enough
    assert await ids(session, same) == ["two-invoices"]


async def test_old_versions_do_not_match_filters(session: AsyncSession) -> None:
    document = await named(session, "doc")
    await add_invoice(session, document, supplier="Old Supplier", version=1, current=False)
    await add_invoice(session, document, supplier="New Supplier", version=2)

    assert await ids(session, DocumentFilters(supplier="old supplier")) == []
    assert await ids(session, DocumentFilters(supplier="new supplier")) == ["doc"]
