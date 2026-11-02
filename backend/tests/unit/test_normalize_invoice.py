from datetime import date
from decimal import Decimal

from app.normalize.invoice import normalize_invoice
from app.schemas.invoice import InvoiceDraft, LineItemDraft


def test_a_complete_draft_becomes_exact_data() -> None:
    draft = InvoiceDraft(
        invoice_number=" INV-1 ",
        invoice_date="5 January 2026",
        supplier_name="Acme Ltd",
        customer_name="Globex",
        subtotal="100,00",
        tax="20.00",
        total="1.020,00",
        currency="€",
        line_items=[LineItemDraft(description="Pen", quantity="2", unit_price="50", amount="100")],
    )

    data, findings = normalize_invoice(draft)

    assert findings == []
    assert data.invoice_number == "INV-1"
    assert data.invoice_date == date(2026, 1, 5)
    assert (data.subtotal, data.tax, data.total) == (
        Decimal("100.00"),
        Decimal("20.00"),
        Decimal("1020.00"),
    )
    assert data.currency == "EUR"
    assert data.line_items[0].amount == Decimal("100")


def test_an_empty_draft_gives_empty_data_and_no_findings() -> None:
    data, findings = normalize_invoice(InvoiceDraft())

    assert data.model_dump(exclude={"line_items"}) == dict.fromkeys(
        ["invoice_number", "invoice_date", "supplier_name", "customer_name"]
        + ["subtotal", "tax", "total", "currency"]
    )
    assert findings == []


def test_unreadable_values_become_none_with_a_warning_each() -> None:
    draft = InvoiceDraft(
        invoice_date="soon",
        total="n/a",
        line_items=[LineItemDraft(description="Pen", amount="lots")],
    )

    data, findings = normalize_invoice(draft)

    assert data.invoice_date is None and data.total is None
    assert data.line_items[0].amount is None
    assert [(f.code, f.field) for f in findings] == [
        ("unparseable_value", "invoice_date"),
        ("unparseable_value", "line_items[0].amount"),
        ("unparseable_value", "total"),
    ]
