from app.pipeline.grounding import ground_invoice
from app.schemas.invoice import FieldNote, InvoiceDraft, LineItemDraft
from app.validation.findings import Finding

TEXT = """ACME Industries Ltd
Invoice No: INV-1042   Date: 5 January 2026
Bill to: Globex Corp
Widget     3     10.00     30.00
Gadget     1     90.50     90.50
Subtotal 120.50   Tax 24.10   Total: 1,234.50 EUR
"""


def codes(findings: list[Finding]) -> list[tuple[str, str | None]]:
    return [(f.code, f.field) for f in findings]


def test_a_value_found_by_its_quote_is_kept() -> None:
    draft = InvoiceDraft(
        invoice_number="INV-1042",
        notes=[FieldNote(field="invoice_number", confidence=0.9, quote="Invoice No: INV-1042")],
    )

    grounded, findings = ground_invoice(draft, TEXT)

    assert grounded.invoice_number == "INV-1042"
    assert findings == []


def test_an_amount_is_found_in_another_number_format() -> None:
    grounded, findings = ground_invoice(InvoiceDraft(total="1234.50"), TEXT)  # text: 1,234.50

    assert grounded.total == "1234.50"
    assert findings == []


def test_a_value_with_a_small_ocr_typo_is_still_found() -> None:
    grounded, findings = ground_invoice(InvoiceDraft(supplier_name="ACME Industrles Ltd"), TEXT)

    assert grounded.supplier_name == "ACME Industrles Ltd"
    assert findings == []


def test_a_field_without_a_note_is_grounded_by_its_value() -> None:
    grounded, _ = ground_invoice(InvoiceDraft(customer_name="Globex Corp", notes=[]), TEXT)

    assert grounded.customer_name == "Globex Corp"


def test_a_supplier_that_is_not_in_the_text_becomes_none_with_a_warning() -> None:
    draft = InvoiceDraft(
        supplier_name="Initech Holdings",
        notes=[FieldNote(field="supplier_name", confidence=0.8, quote="Initech Holdings")],
    )

    grounded, findings = ground_invoice(draft, TEXT)

    assert grounded.supplier_name is None
    assert codes(findings) == [("ungrounded_field", "supplier_name")]
    assert grounded.notes == []  # the note about the removed value goes with it


def test_an_amount_that_is_not_in_the_text_is_removed() -> None:
    grounded, findings = ground_invoice(InvoiceDraft(total="999.99"), TEXT)

    assert grounded.total is None
    assert codes(findings) == [("ungrounded_field", "total")]


def test_blank_values_become_none_without_a_warning() -> None:
    grounded, findings = ground_invoice(InvoiceDraft(tax="  ", currency=""), TEXT)

    assert grounded.tax is None and grounded.currency is None
    assert findings == []


def test_a_line_item_that_is_not_in_the_text_is_dropped_with_a_warning() -> None:
    draft = InvoiceDraft(
        line_items=[
            LineItemDraft(description="Widget", quantity="3", unit_price="10.00", amount="30.00"),
            LineItemDraft(description="Invisible service", amount="55.00"),
            LineItemDraft(description="Gadget", amount="12.00"),  # amount is not in the text
        ]
    )

    grounded, findings = ground_invoice(draft, TEXT)

    assert [item.description for item in grounded.line_items] == ["Widget"]
    assert codes(findings) == [("ungrounded_field", "line_items")] * 2
