"""Stand-ins for the model, shared by the extraction tests."""

from collections.abc import Sequence

from app.llm.extract import ExtractedInvoice
from app.schemas.invoice import FieldNote, InvoiceDraft

TEXT = (
    "Invoice INV-1\nAcme Ltd\nBill to Globex\nDate 5 January 2026\n"
    "Subtotal 100.00 Tax 20.00 Total 120.00 EUR"
)


def draft(**overrides: object) -> InvoiceDraft:
    """A clean invoice that is fully present in TEXT."""
    fields: dict[str, object] = {
        "invoice_number": "INV-1",
        "invoice_date": "5 January 2026",
        "supplier_name": "Acme Ltd",
        "customer_name": "Globex",
        "subtotal": "100.00",
        "tax": "20.00",
        "total": "120.00",
        "currency": "EUR",
        "notes": [
            FieldNote(field="invoice_number", confidence=0.95, quote="Invoice INV-1"),
            FieldNote(field="total", confidence=0.9, quote="Total 120.00"),
        ],
    }
    fields.update(overrides)
    return InvoiceDraft(**fields)


class FakeExtractor:
    """Stands in for the model: returns the invoices it was given."""

    def __init__(self, drafts: Sequence[InvoiceDraft], text: str = TEXT) -> None:
        self.items = [ExtractedInvoice(d, text, "fake-model") for d in drafts]

    def extract(self, pages: Sequence[tuple[int, str]]) -> list[ExtractedInvoice]:
        return self.items
