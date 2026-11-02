"""Invoice shapes: what the model returns (drafts, all text) and what is stored (data, exact).

The model returns every value as text and the code turns it into numbers and dates, so a binary
float is never involved. Every field is optional: a field the document does not state is None.
"""

from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# Names used in notes, confidences, quotes and findings.
SCALAR_FIELDS = (
    "invoice_number",
    "invoice_date",
    "supplier_name",
    "customer_name",
    "subtotal",
    "tax",
    "total",
    "currency",
)
AMOUNT_FIELDS = ("subtotal", "tax", "total")


class LineItemDraft(BaseModel):
    description: str | None = Field(default=None, description="What was sold, as written")
    quantity: str | None = Field(default=None, description="Quantity as written")
    unit_price: str | None = Field(default=None, description="Price of one unit as written")
    amount: str | None = Field(default=None, description="Line total as written")


class FieldNote(BaseModel):
    """How sure the model is about one field and where in the text it read it."""

    field: str = Field(description="Field name, e.g. invoice_number, total, supplier_name")
    confidence: float = Field(ge=0, le=1, description="0 (a guess) to 1 (clearly stated)")
    quote: str | None = Field(default=None, description="The exact words the value came from")


class InvoiceDraft(BaseModel):
    invoice_number: str | None = Field(default=None, description="Invoice number or ID")
    invoice_date: str | None = Field(default=None, description="Invoice date as written")
    supplier_name: str | None = Field(default=None, description="Who issued the invoice")
    customer_name: str | None = Field(default=None, description="Who the invoice is addressed to")
    subtotal: str | None = Field(default=None, description="Amount before tax, as written")
    tax: str | None = Field(default=None, description="Tax amount, as written")
    total: str | None = Field(default=None, description="Total to pay, as written")
    currency: str | None = Field(default=None, description="Currency code or symbol as written")
    line_items: list[LineItemDraft] = Field(default_factory=list)
    notes: list[FieldNote] = Field(default_factory=list)


class ExtractionResult(BaseModel):
    invoices: list[InvoiceDraft] = Field(
        default_factory=list, description="Every invoice in the text; empty if there is none"
    )


class LineItemData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str | None = None
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    amount: Decimal | None = None


class InvoiceData(BaseModel):
    """A normalized invoice. Amounts are Decimal, the date is a calendar date."""

    model_config = ConfigDict(extra="forbid")

    invoice_number: str | None = None
    invoice_date: date | None = None
    supplier_name: str | None = None
    customer_name: str | None = None
    subtotal: Decimal | None = None
    tax: Decimal | None = None
    total: Decimal | None = None
    currency: str | None = None
    line_items: list[LineItemData] = Field(default_factory=list)

    def to_jsonable(self) -> dict[str, Any]:
        """For the JSONB column: amounts become strings, the date ISO 8601."""
        return self.model_dump(mode="json")
