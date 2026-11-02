"""Compares the invoices of two documents. Pure: no database, storage or web imports."""

import re
import uuid
from dataclasses import dataclass
from decimal import Decimal

from app.normalize.values import normalize_name
from app.schemas.invoice import InvoiceData

# Amounts that differ by no more than this are the same (rounding).
AMOUNT_TOLERANCE = Decimal("0.01")

MATCH = "match"
MISMATCH = "mismatch"
UNMATCHED = "unmatched"


@dataclass(frozen=True)
class Candidate:
    """One stored invoice, as the comparison sees it."""

    extraction_id: uuid.UUID
    data: InvoiceData


@dataclass(frozen=True)
class Diff:
    field: str
    left: str | None
    right: str | None


@dataclass(frozen=True)
class Pair:
    """Two invoices that were matched, or one invoice (the other side None) that was not."""

    left: Candidate | None
    right: Candidate | None
    match_key: str | None
    status: str
    diffs: list[Diff]


def _number_key(data: InvoiceData) -> str | None:
    """The invoice number without case, spaces or punctuation: "INV-007" equals "inv 007"."""
    key = re.sub(r"[^0-9a-z]", "", (data.invoice_number or "").casefold())
    return key or None


def _same_amount(a: Decimal | None, b: Decimal | None) -> bool:
    if a is None or b is None:
        return a is b
    return abs(a - b) <= AMOUNT_TOLERANCE


def _same_supplier_and_total(left: InvoiceData, right: InvoiceData) -> bool:
    supplier = normalize_name(left.supplier_name)
    return (
        supplier is not None
        and supplier == normalize_name(right.supplier_name)
        and left.total is not None
        and _same_amount(left.total, right.total)
    )


def match(left: list[Candidate], right: list[Candidate]) -> list[Pair]:
    """Pair each left invoice with at most one right invoice, then list what is left over.

    By invoice number first (for every left invoice, so a number match is never stolen by a
    looser match), then by supplier and total. Pairs come in left order, then unmatched right.
    """
    free = list(right)
    found: dict[int, tuple[Candidate, str]] = {}  # position in `left` -> right invoice, key

    for position, invoice in enumerate(left):
        number = _number_key(invoice.data)
        if number is None:
            continue
        other = next((r for r in free if _number_key(r.data) == number), None)
        if other is not None:
            free.remove(other)
            found[position] = (other, number)

    for position, invoice in enumerate(left):
        if position in found:
            continue
        other = next((r for r in free if _same_supplier_and_total(invoice.data, r.data)), None)
        if other is not None:
            free.remove(other)
            key = f"{normalize_name(invoice.data.supplier_name)}|{invoice.data.total}"
            found[position] = (other, key)

    pairs = []
    for position, invoice in enumerate(left):
        if position in found:
            other, key = found[position]
            diffs = compare(invoice.data, other.data)
            pairs.append(Pair(invoice, other, key, MISMATCH if diffs else MATCH, diffs))
        else:
            pairs.append(Pair(invoice, None, None, UNMATCHED, []))
    pairs += [Pair(None, other, None, UNMATCHED, []) for other in free]
    return pairs


def compare(left: InvoiceData, right: InvoiceData) -> list[Diff]:
    """Every field in which two invoices differ."""
    diffs: list[Diff] = []

    def check(field: str, a: object, b: object, same: bool) -> None:
        if not same:
            diffs.append(Diff(field, None if a is None else str(a), None if b is None else str(b)))

    check(
        "invoice_date",
        left.invoice_date,
        right.invoice_date,
        left.invoice_date == right.invoice_date,
    )
    check(
        "supplier_name",
        left.supplier_name,
        right.supplier_name,
        normalize_name(left.supplier_name) == normalize_name(right.supplier_name),
    )
    check(
        "customer_name",
        left.customer_name,
        right.customer_name,
        normalize_name(left.customer_name) == normalize_name(right.customer_name),
    )
    for field in ("subtotal", "tax", "total"):
        a, b = getattr(left, field), getattr(right, field)
        check(field, a, b, _same_amount(a, b))
    check(
        "currency",
        left.currency,
        right.currency,
        (left.currency or "").casefold() == (right.currency or "").casefold(),
    )
    check(
        "line_item_count",
        len(left.line_items),
        len(right.line_items),
        len(left.line_items) == len(right.line_items),
    )
    sums = [sum((i.amount or Decimal(0) for i in d.line_items), Decimal(0)) for d in (left, right)]
    check("line_item_sum", sums[0], sums[1], _same_amount(sums[0], sums[1]))
    return diffs
