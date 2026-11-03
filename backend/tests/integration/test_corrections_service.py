import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Correction, Document, DocumentStatus, Extraction, ValidationIssue
from app.schemas.invoice import FieldNote, InvoiceData
from app.services.corrections import (
    DocumentBusy,
    InvalidCorrection,
    InvoiceNotFound,
    correct_invoice,
)
from app.services.errors import DocumentNotFound
from tests.invoice_fakes import THRESHOLD, TODAY, draft, extracted_document

WRONG_TOTAL = draft(total="130.00")  # 100.00 + 20.00 is not 130.00


async def fix(
    session: AsyncSession, document: Document, fields: dict[str, object], index: int = 0
) -> Extraction:
    return await correct_invoice(session, document.id, index, fields, "reviewer", TODAY, THRESHOLD)


async def versions(session: AsyncSession, document: Document) -> list[Extraction]:
    rows = await session.scalars(
        select(Extraction)
        .where(Extraction.document_id == document.id)
        .order_by(Extraction.invoice_index, Extraction.version)
        .execution_options(populate_existing=True)
    )
    return list(rows)


async def findings(session: AsyncSession, extraction: Extraction) -> set[str]:
    rows = await session.scalars(
        select(ValidationIssue.code).where(ValidationIssue.extraction_id == extraction.id)
    )
    return set(rows)


async def status_of(session: AsyncSession, document: Document) -> str:
    await session.refresh(document)
    return document.status


async def test_a_fixed_total_is_a_new_version_and_the_old_one_is_kept(
    session: AsyncSession,
) -> None:
    document = await extracted_document(session, [WRONG_TOTAL])

    new = await fix(session, document, {"total": "120.00"})

    old, current = await versions(session, document)
    assert (old.version, old.is_current, old.data["total"]) == (1, False, "130.00")
    assert (current.version, current.is_current, current.data["total"]) == (2, True, "120.00")
    assert current.id == new.id and (new.model, new.prompt_version) == ("manual", "manual")
    assert new.total == Decimal("120.00")  # the lookup column follows the data


async def test_values_are_normalized_like_extracted_ones(session: AsyncSession) -> None:
    document = await extracted_document(session, [draft()])

    new = await fix(session, document, {"invoice_date": "6 January 2026", "currency": "£"})

    assert new.data["invoice_date"] == "2026-01-06" and new.data["currency"] == "GBP"
    assert new.invoice_date is not None and new.currency == "GBP"


async def test_a_field_can_be_cleared(session: AsyncSession) -> None:
    document = await extracted_document(session, [draft()])

    new = await fix(session, document, {"customer_name": None})

    assert new.data["customer_name"] is None


async def test_line_items_are_replaced_as_a_whole(session: AsyncSession) -> None:
    document = await extracted_document(session, [draft()])
    lines = [
        {"description": "Pen", "quantity": "2", "unit_price": "1.50", "amount": "3.00"},
        {"description": "Ink", "amount": 4},
    ]

    new = await fix(session, document, {"line_items": lines})

    saved = InvoiceData.model_validate(new.data).line_items
    assert [(i.description, i.amount) for i in saved] == [
        ("Pen", Decimal("3.00")),
        ("Ink", Decimal("4")),
    ]


@pytest.mark.parametrize(
    ("fields", "bad_field"),
    [
        ({"total": "lots"}, "total"),
        ({"invoice_date": "soon"}, "invoice_date"),
        ({"line_items": [{"amount": "many"}]}, "line_items[0].amount"),
        ({"line_items": "not a list"}, "line_items"),
        ({"line_items": [{"colour": "red"}]}, "line_items[0]"),
        ({"colour": "red"}, "colour"),
        ({"total": True}, "total"),
    ],
)
async def test_an_invalid_patch_is_rejected_and_nothing_is_saved(
    session: AsyncSession, fields: dict[str, object], bad_field: str
) -> None:
    document = await extracted_document(session, [draft()])

    with pytest.raises(InvalidCorrection) as error:
        await fix(session, document, fields)

    assert error.value.field == bad_field
    assert len(await versions(session, document)) == 1


async def test_an_unchanged_value_saves_nothing(session: AsyncSession) -> None:
    document = await extracted_document(session, [draft()])

    same = await fix(session, document, {"total": "120.00", "currency": "eur"})

    assert same.version == 1
    assert len(await versions(session, document)) == 1
    assert (await session.scalars(select(Correction))).all() == []


async def test_every_changed_field_gets_an_audit_row_and_unchanged_ones_do_not(
    session: AsyncSession,
) -> None:
    document = await extracted_document(session, [draft()])

    new = await fix(session, document, {"total": "125.00", "currency": "USD", "tax": "20.00"})

    rows = (await session.scalars(select(Correction).order_by(Correction.field))).all()
    assert [(r.field, r.old_value, r.new_value) for r in rows] == [
        ("currency", "EUR", "USD"),
        ("total", "120.00", "125.00"),
    ]  # tax was sent but did not change
    assert {r.edited_by for r in rows} == {"reviewer"}
    assert {r.extraction_id for r in rows} == {new.id}
    assert all(r.document_id == document.id and r.created_at is not None for r in rows)


async def test_edited_fields_are_fully_trusted_and_the_others_keep_their_score(
    session: AsyncSession,
) -> None:
    unsure = draft(
        notes=[
            FieldNote(field="supplier_name", confidence=0.3, quote="Acme Ltd"),
            FieldNote(field="invoice_number", confidence=0.9, quote="Invoice INV-1"),
        ]
    )
    document = await extracted_document(session, [unsure])
    assert await status_of(session, document) == DocumentStatus.NEEDS_REVIEW  # low confidence

    new = await fix(session, document, {"supplier_name": "Acme Industries Ltd"})

    assert new.field_confidence == {"supplier_name": 1.0, "invoice_number": 0.9}
    assert "supplier_name" not in new.grounding and "invoice_number" in new.grounding
    assert "low_confidence" not in await findings(session, new)
    assert await status_of(session, document) == DocumentStatus.COMPLETED


async def test_fixing_the_only_error_completes_the_document(session: AsyncSession) -> None:
    document = await extracted_document(session, [WRONG_TOTAL])
    assert await status_of(session, document) == DocumentStatus.NEEDS_REVIEW

    new = await fix(session, document, {"total": "120.00"})

    assert "total_mismatch" not in await findings(session, new)
    assert await status_of(session, document) == DocumentStatus.COMPLETED


async def test_an_edit_that_breaks_the_totals_sends_the_document_for_review(
    session: AsyncSession,
) -> None:
    document = await extracted_document(session, [draft()])
    assert await status_of(session, document) == DocumentStatus.COMPLETED

    new = await fix(session, document, {"total": "130.00"})

    assert "total_mismatch" in await findings(session, new)
    assert await status_of(session, document) == DocumentStatus.NEEDS_REVIEW


async def test_another_invoice_with_an_error_keeps_the_document_in_review(
    session: AsyncSession,
) -> None:
    document = await extracted_document(session, [WRONG_TOTAL, WRONG_TOTAL])

    await fix(session, document, {"total": "120.00"}, index=0)

    assert await status_of(session, document) == DocumentStatus.NEEDS_REVIEW
    first, second = [e for e in await versions(session, document) if e.is_current]
    assert "total_mismatch" not in await findings(session, first)
    assert "total_mismatch" in await findings(session, second)  # untouched, still reported


@pytest.mark.parametrize("busy", [DocumentStatus.PROCESSING, DocumentStatus.QUEUED])
async def test_a_document_that_is_being_processed_cannot_be_edited(
    session: AsyncSession, busy: DocumentStatus
) -> None:
    document = await extracted_document(session, [draft()])
    document.status = busy
    await session.commit()

    with pytest.raises(DocumentBusy):
        await fix(session, document, {"total": "125.00"})


async def test_an_unknown_invoice_or_document_is_not_found(session: AsyncSession) -> None:
    document = await extracted_document(session, [draft(), draft()])

    with pytest.raises(InvoiceNotFound):
        await fix(session, document, {"total": "1"}, index=5)
    with pytest.raises(DocumentNotFound):
        await correct_invoice(session, uuid.uuid4(), 0, {"total": "1"}, "x", TODAY, THRESHOLD)
