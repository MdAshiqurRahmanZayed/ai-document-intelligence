"""Turns a grounded draft (text values) into stored invoice data (exact values)."""

from decimal import Decimal

from app.normalize.values import normalize_currency, parse_amount, parse_date
from app.schemas.invoice import InvoiceData, InvoiceDraft, LineItemData
from app.validation.findings import WARNING, Finding


def normalize_invoice(draft: InvoiceDraft) -> tuple[InvoiceData, list[Finding]]:
    """Parse the draft's text into Decimal amounts, a date and an ISO 4217 currency.

    A value that is present but cannot be read becomes None with an `unparseable_value` warning.
    """
    findings: list[Finding] = []

    def amount(raw: str | None, field: str) -> Decimal | None:
        parsed = parse_amount(raw)
        if raw and raw.strip() and parsed is None:
            findings.append(_unreadable(field, raw))
        return parsed

    invoice_date = parse_date(draft.invoice_date)
    if draft.invoice_date and draft.invoice_date.strip() and invoice_date is None:
        findings.append(_unreadable("invoice_date", draft.invoice_date))

    lines = [
        LineItemData(
            description=(item.description or "").strip() or None,
            quantity=amount(item.quantity, f"line_items[{position}].quantity"),
            unit_price=amount(item.unit_price, f"line_items[{position}].unit_price"),
            amount=amount(item.amount, f"line_items[{position}].amount"),
        )
        for position, item in enumerate(draft.line_items)
    ]
    data = InvoiceData(
        invoice_number=(draft.invoice_number or "").strip() or None,
        invoice_date=invoice_date,
        supplier_name=(draft.supplier_name or "").strip() or None,
        customer_name=(draft.customer_name or "").strip() or None,
        subtotal=amount(draft.subtotal, "subtotal"),
        tax=amount(draft.tax, "tax"),
        total=amount(draft.total, "total"),
        currency=normalize_currency(draft.currency),
        line_items=lines,
    )
    return data, findings


def _unreadable(field: str, raw: str) -> Finding:
    return Finding("unparseable_value", WARNING, f"{field} '{raw}' could not be read", field)
