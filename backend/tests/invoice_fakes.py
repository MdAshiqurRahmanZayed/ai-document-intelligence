"""Stand-ins for the model, shared by the extraction tests."""

from collections.abc import Sequence
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, Page
from app.llm.extract import ExtractedInvoice
from app.schemas.invoice import FieldNote, InvoiceDraft
from app.services.extraction import run_extraction
from tests.helpers import make_document

TODAY = date(2026, 6, 1)
THRESHOLD = 0.5

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


async def stored_document(session: AsyncSession, text: str = TEXT) -> Document:
    """A document whose text is ready: the state in which extraction starts."""
    document = make_document()
    session.add(document)
    await session.commit()
    session.add(Page(document_id=document.id, page_no=1, text=text, method="native"))
    await session.commit()
    return document


async def extracted_document(
    session: AsyncSession, drafts: Sequence[InvoiceDraft], text: str = TEXT
) -> Document:
    """A document that went through extraction and validation with a fake model."""
    document = await stored_document(session, text)
    await run_extraction(session, document, FakeExtractor(drafts, text), TODAY, THRESHOLD)
    return document
