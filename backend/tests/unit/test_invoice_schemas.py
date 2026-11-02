from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.invoice import ExtractionResult, InvoiceData, InvoiceDraft, LineItemData


def test_an_empty_draft_is_valid_and_every_field_is_none() -> None:
    draft = InvoiceDraft()
    assert draft.model_dump(exclude={"line_items", "notes"}) == dict.fromkeys(
        ["invoice_number", "invoice_date", "supplier_name", "customer_name"]
        + ["subtotal", "tax", "total", "currency"]
    )
    assert draft.line_items == [] and draft.notes == []
    assert ExtractionResult().invoices == []


def test_invoice_data_round_trips_through_json_with_amounts_as_strings() -> None:
    data = InvoiceData(
        invoice_number="INV-1",
        invoice_date=date(2026, 1, 5),
        total=Decimal("120.50"),
        line_items=[LineItemData(description="Pen", quantity=Decimal("3"), amount=Decimal("1.5"))],
    )

    stored = data.to_jsonable()

    assert stored["total"] == "120.50"  # a string, never a float
    assert stored["invoice_date"] == "2026-01-05"
    assert stored["line_items"][0]["amount"] == "1.5"
    assert InvoiceData.model_validate(stored) == data


def test_unknown_fields_are_rejected_in_stored_data() -> None:
    with pytest.raises(ValidationError):
        InvoiceData.model_validate({"invoice_number": "INV-1", "colour": "red"})
