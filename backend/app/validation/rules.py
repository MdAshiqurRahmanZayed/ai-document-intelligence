"""Business rules for one extracted invoice, and the decision to send a document for review.

Pure functions of the invoice data: no database, storage or web imports.
"""

from collections.abc import Iterable, Mapping
from datetime import date
from decimal import Decimal

import pycountry

from app.db.models.document import DocumentStatus
from app.schemas.invoice import AMOUNT_FIELDS, SCALAR_FIELDS, InvoiceData
from app.validation.findings import ERROR, WARNING, Finding

REQUIRED_FIELDS = ("invoice_number", "invoice_date", "supplier_name", "total")
MAX_AMOUNT = Decimal("1000000000000")
OLDEST_DATE = date(2000, 1, 1)
MAX_TAX_RATE = Decimal("0.30")
# Amounts are compared with a tolerance for rounding: the larger of a flat 0.02 and 0.5 percent.
MIN_TOLERANCE = Decimal("0.02")
TOLERANCE_RATE = Decimal("0.005")
VALID_CURRENCIES = frozenset(currency.alpha_3 for currency in pycountry.currencies)


def tolerance(reference: Decimal) -> Decimal:
    return max(MIN_TOLERANCE, TOLERANCE_RATE * abs(reference))


def validate_invoice(
    data: InvoiceData, confidence: Mapping[str, float], today: date, threshold: float
) -> list[Finding]:
    findings: list[Finding] = []
    findings += _required_fields(data)
    findings += _amount_checks(data)
    findings += _totals_checks(data)
    findings += _date_checks(data, today)
    findings += _currency_checks(data)
    findings += _confidence_checks(data, confidence, threshold)
    return findings


def _required_fields(data: InvoiceData) -> list[Finding]:
    return [
        Finding("missing_field", ERROR, f"{field} is missing", field)
        for field in REQUIRED_FIELDS
        if getattr(data, field) is None
    ]


def _named_amounts(data: InvoiceData) -> Iterable[tuple[str, Decimal]]:
    """Every amount of the invoice with the name findings use for it."""
    for field in AMOUNT_FIELDS:
        value = getattr(data, field)
        if value is not None:
            yield field, value
    for position, line in enumerate(data.line_items):
        for name in ("quantity", "unit_price", "amount"):
            value = getattr(line, name)
            if value is not None:
                yield f"line_items[{position}].{name}", value


def _amount_checks(data: InvoiceData) -> list[Finding]:
    findings = []
    for name, value in _named_amounts(data):
        if value < 0:
            findings.append(
                Finding("negative_amount", ERROR, f"{name} is negative ({value})", name)
            )
        elif value > MAX_AMOUNT:
            findings.append(Finding("implausible_amount", ERROR, f"{name} is too large", name))
    for position, line in enumerate(data.line_items):
        if line.quantity is None or line.unit_price is None or line.amount is None:
            continue
        expected = line.quantity * line.unit_price
        if abs(expected - line.amount) > MIN_TOLERANCE:
            message = (
                f"line {position + 1}: {line.quantity} x {line.unit_price} is {expected}, "
                f"not {line.amount}"
            )
            findings.append(
                Finding("line_amount_mismatch", WARNING, message, f"line_items[{position}].amount")
            )
    return findings


def _totals_checks(data: InvoiceData) -> list[Finding]:
    findings = []
    amounts = [line.amount for line in data.line_items]
    # A line without an amount makes the sum incomplete, so it cannot be compared.
    if data.subtotal is not None and amounts and all(a is not None for a in amounts):
        total_of_lines = sum((a for a in amounts if a is not None), Decimal(0))
        if abs(total_of_lines - data.subtotal) > tolerance(data.subtotal):
            message = f"line items add up to {total_of_lines}, but the subtotal is {data.subtotal}"
            findings.append(Finding("line_items_sum_mismatch", ERROR, message, "subtotal"))
    if data.subtotal is not None and data.tax is not None and data.total is not None:
        expected = data.subtotal + data.tax
        if abs(expected - data.total) > tolerance(data.subtotal):
            message = (
                f"subtotal {data.subtotal} plus tax {data.tax} is {expected}, not {data.total}"
            )
            findings.append(Finding("total_mismatch", ERROR, message, "total"))
    if data.subtotal and data.tax is not None:  # a zero or missing subtotal has no tax rate
        rate = data.tax / data.subtotal
        if rate < 0 or rate > MAX_TAX_RATE:
            message = f"tax rate of {rate:.1%} is outside 0 to {MAX_TAX_RATE:.0%}"
            findings.append(Finding("implausible_tax_rate", WARNING, message, "tax"))
    return findings


def _date_checks(data: InvoiceData, today: date) -> list[Finding]:
    if data.invoice_date is None:
        return []
    if data.invoice_date > today:
        return [
            Finding(
                "future_date",
                ERROR,
                f"invoice date {data.invoice_date} is in the future",
                "invoice_date",
            )
        ]
    if data.invoice_date < OLDEST_DATE:
        return [
            Finding(
                "old_date",
                WARNING,
                f"invoice date {data.invoice_date} is before {OLDEST_DATE.year}",
                "invoice_date",
            )
        ]
    return []


def _currency_checks(data: InvoiceData) -> list[Finding]:
    if data.currency is None:
        return [Finding("missing_currency", WARNING, "currency is missing", "currency")]
    if data.currency not in VALID_CURRENCIES:
        return [
            Finding(
                "invalid_currency",
                ERROR,
                f"'{data.currency}' is not an ISO 4217 currency",
                "currency",
            )
        ]
    return []


def _confidence_checks(
    data: InvoiceData, confidence: Mapping[str, float], threshold: float
) -> list[Finding]:
    return [
        Finding(
            "low_confidence",
            WARNING,
            f"{field} was read with confidence {confidence[field]:.2f}",
            field,
        )
        for field in SCALAR_FIELDS
        if getattr(data, field) is not None and confidence.get(field, 1.0) < threshold
    ]


def route(findings: Iterable[Finding], has_invoices: bool) -> str:
    """The status of a document after validation: a person looks at it, or it is done."""
    needs_review = not has_invoices or any(
        f.severity == ERROR or f.code == "low_confidence" for f in findings
    )
    return DocumentStatus.NEEDS_REVIEW if needs_review else DocumentStatus.COMPLETED
