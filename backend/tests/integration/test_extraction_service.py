from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, DocumentStatus, Extraction, Page, ValidationIssue
from app.schemas.invoice import InvoiceDraft
from app.services.extraction import (
    extract_document_invoices,
    run_extraction,
    validate_document,
)
from tests.helpers import make_document
from tests.invoice_fakes import TEXT, FakeExtractor, draft

TODAY = date(2026, 6, 1)
THRESHOLD = 0.5


async def stored(session: AsyncSession, text: str = TEXT) -> Document:
    document = make_document()
    session.add(document)
    await session.commit()
    session.add(Page(document_id=document.id, page_no=1, text=text, method="native"))
    await session.commit()
    return document


async def extractions_of(session: AsyncSession, document: Document) -> list[Extraction]:
    result = await session.scalars(
        select(Extraction)
        .where(Extraction.document_id == document.id)
        .order_by(Extraction.version, Extraction.invoice_index)
        .execution_options(populate_existing=True)
    )
    return list(result)


async def issues_of(session: AsyncSession, document: Document) -> list[ValidationIssue]:
    result = await session.scalars(
        select(ValidationIssue)
        .where(ValidationIssue.document_id == document.id)
        .execution_options(populate_existing=True)
    )
    return list(result)


async def finish(
    session: AsyncSession, document: Document, drafts: Sequence[InvoiceDraft], text: str = TEXT
) -> None:
    """Run the whole job for the document."""
    await run_extraction(session, document, FakeExtractor(drafts, text), TODAY, THRESHOLD)


# --- saving extractions -------------------------------------------------------------------


async def test_an_invoice_is_saved_with_its_values_confidence_and_provenance(
    session: AsyncSession,
) -> None:
    document = await stored(session)

    await extract_document_invoices(session, document, FakeExtractor([draft()]))

    (saved,) = await extractions_of(session, document)
    assert (saved.invoice_index, saved.version, saved.is_current) == (0, 1, True)
    assert saved.data["total"] == "120.00" and saved.data["invoice_date"] == "2026-01-05"
    assert (saved.invoice_number, saved.supplier_norm, saved.currency) == ("INV-1", "acme", "EUR")
    assert (saved.total, saved.invoice_date) == (Decimal("120.00"), date(2026, 1, 5))
    assert saved.field_confidence == {"invoice_number": 0.95, "total": 0.9}
    assert saved.grounding == {"invoice_number": "Invoice INV-1", "total": "Total 120.00"}
    assert (saved.model, saved.prompt_version) == ("fake-model", "v1")


async def test_several_invoices_are_numbered_from_zero(session: AsyncSession) -> None:
    document = await stored(session)

    await extract_document_invoices(session, document, FakeExtractor([draft(), draft(), draft()]))

    assert [e.invoice_index for e in await extractions_of(session, document)] == [0, 1, 2]


async def test_missing_fields_stay_empty(session: AsyncSession) -> None:
    document = await stored(session)

    await extract_document_invoices(
        session,
        document,
        FakeExtractor([draft(customer_name=None, tax=None, notes=[])]),
    )

    (saved,) = await extractions_of(session, document)
    assert saved.data["customer_name"] is None and saved.data["tax"] is None


async def test_a_value_that_is_not_in_the_text_is_not_saved(session: AsyncSession) -> None:
    document = await stored(session)

    records = await extract_document_invoices(
        session,
        document,
        FakeExtractor([draft(supplier_name="Initech Holdings")]),
    )

    assert records[0].data.supplier_name is None
    assert [(f.code, f.field) for f in records[0].findings] == [
        ("ungrounded_field", "supplier_name")
    ]


async def test_a_rerun_adds_version_two_and_retires_version_one(session: AsyncSession) -> None:
    document = await stored(session)
    extractor = FakeExtractor([draft()])

    await extract_document_invoices(session, document, extractor)
    await extract_document_invoices(session, document, extractor)

    first, second = await extractions_of(session, document)
    assert (first.version, first.is_current) == (1, False)
    assert (second.version, second.is_current) == (2, True)


async def test_a_document_without_invoices_saves_nothing(session: AsyncSession) -> None:
    document = await stored(session)

    assert await extract_document_invoices(session, document, FakeExtractor([])) == []
    assert await extractions_of(session, document) == []


# --- validation, duplicates and routing ----------------------------------------------------


def codes(issues: Sequence[ValidationIssue]) -> set[tuple[str, str]]:
    return {(i.code, i.severity) for i in issues}


async def test_a_clean_invoice_completes_the_document(session: AsyncSession) -> None:
    document = await stored(session)

    await finish(session, document, [draft()])

    await session.refresh(document)
    assert document.status == DocumentStatus.COMPLETED
    assert await issues_of(session, document) == []


async def test_an_invoice_with_an_error_needs_review(session: AsyncSession) -> None:
    document = await stored(session, TEXT.replace("Total 120.00", "Total 130.00"))

    await finish(
        session, document, [draft(total="130.00")], TEXT.replace("Total 120.00", "Total 130.00")
    )

    await session.refresh(document)
    assert document.status == DocumentStatus.NEEDS_REVIEW
    assert ("total_mismatch", "error") in codes(await issues_of(session, document))


async def test_warnings_alone_do_not_need_review(session: AsyncSession) -> None:
    text = TEXT.replace("5 January 2026", "5 January 1999")
    document = await stored(session, text)

    await finish(session, document, [draft(invoice_date="5 January 1999")], text)

    await session.refresh(document)
    assert document.status == DocumentStatus.COMPLETED
    assert codes(await issues_of(session, document)) == {("old_date", "warning")}


async def test_a_document_without_an_invoice_needs_review(session: AsyncSession) -> None:
    document = await stored(session, "Dear customer, thank you for your order.")

    await finish(session, document, [])

    await session.refresh(document)
    assert document.status == DocumentStatus.NEEDS_REVIEW
    (issue,) = await issues_of(session, document)
    assert (issue.code, issue.extraction_id) == ("no_invoice_found", None)


async def test_the_same_number_and_supplier_under_another_spelling_is_a_duplicate(
    session: AsyncSession,
) -> None:
    first, second = (
        await stored(session),
        await stored(session, TEXT.replace("Acme Ltd", "ACME Ltd.")),
    )
    await finish(session, first, [draft()])

    await finish(
        session, second, [draft(supplier_name="ACME Ltd.")], TEXT.replace("Acme Ltd", "ACME Ltd.")
    )

    await session.refresh(second)
    duplicate = next(i for i in await issues_of(session, second) if i.code == "duplicate_invoice")
    assert (duplicate.severity, duplicate.related_document_id) == ("error", first.id)
    assert second.status == DocumentStatus.NEEDS_REVIEW


async def test_same_supplier_total_and_date_with_another_number_is_a_possible_duplicate(
    session: AsyncSession,
) -> None:
    other_text = TEXT.replace("INV-1", "INV-2")
    first, second = await stored(session), await stored(session, other_text)
    await finish(session, first, [draft()])

    await finish(session, second, [draft(invoice_number="INV-2", notes=[])], other_text)

    await session.refresh(second)
    (possible,) = [i for i in await issues_of(session, second) if i.code == "possible_duplicate"]
    assert (possible.severity, possible.related_document_id) == ("warning", first.id)
    assert second.status == DocumentStatus.COMPLETED  # a warning does not send it for review


async def test_another_supplier_with_the_same_number_is_not_a_duplicate(
    session: AsyncSession,
) -> None:
    text = TEXT.replace("Acme Ltd", "Initech Ltd")
    first, second = await stored(session), await stored(session, text)
    await finish(session, first, [draft()])

    await finish(session, second, [draft(supplier_name="Initech Ltd")], text)

    assert not {"duplicate_invoice", "possible_duplicate"} & {
        i.code for i in await issues_of(session, second)
    }


async def test_a_document_is_not_a_duplicate_of_its_own_earlier_run(session: AsyncSession) -> None:
    document = await stored(session)

    await finish(session, document, [draft()])
    await finish(session, document, [draft()])

    assert await issues_of(session, document) == []


async def test_validating_again_replaces_the_findings(session: AsyncSession) -> None:
    text = TEXT.replace("Total 120.00", "Total 130.00")
    document = await stored(session, text)
    records = await extract_document_invoices(
        session,
        document,
        FakeExtractor([draft(total="130.00")], text),
    )

    for _ in range(2):
        await validate_document(session, document, records, TODAY, THRESHOLD)
        await session.commit()

    assert [i.code for i in await issues_of(session, document)] == ["total_mismatch"]
