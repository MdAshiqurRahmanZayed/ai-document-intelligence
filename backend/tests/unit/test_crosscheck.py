import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from app.schemas.invoice import InvoiceData, LineItemData
from app.validation.crosscheck import MATCH, MISMATCH, UNMATCHED, Candidate, compare, match


def candidate(**overrides: Any) -> Candidate:
    fields: dict[str, Any] = {
        "invoice_number": "INV-7",
        "invoice_date": date(2026, 1, 5),
        "supplier_name": "Acme Ltd",
        "customer_name": "Globex",
        "subtotal": Decimal("100.00"),
        "tax": Decimal("20.00"),
        "total": Decimal("120.00"),
        "currency": "EUR",
        "line_items": [
            LineItemData(amount=Decimal("40.00")),
            LineItemData(amount=Decimal("60.00")),
        ],
    }
    fields.update(overrides)
    return Candidate(uuid.uuid4(), InvoiceData(**fields))


def test_invoices_are_matched_by_number_ignoring_case_spaces_and_punctuation() -> None:
    left, right = candidate(invoice_number="INV-007"), candidate(invoice_number="inv 007")

    (pair,) = match([left], [right])

    assert (pair.left, pair.right, pair.match_key) == (left, right, "inv007")
    assert pair.status == MATCH and pair.diffs == []


def test_without_a_number_they_are_matched_by_supplier_and_total() -> None:
    left = candidate(invoice_number=None, supplier_name="Acme Ltd.")
    right = candidate(invoice_number="INV-9", supplier_name="ACME limited")

    (pair,) = match([left], [right])

    assert pair.right is right
    assert pair.status == MATCH
    assert pair.match_key == "acme|120.00"


def test_a_different_supplier_or_total_is_not_a_fallback_match() -> None:
    left = candidate(invoice_number=None)

    pairs = match(
        [left],
        [
            candidate(invoice_number="A", supplier_name="Initech"),
            candidate(invoice_number="B", total=Decimal("99")),
        ],
    )

    assert [p.status for p in pairs] == [UNMATCHED, UNMATCHED, UNMATCHED]


def test_a_right_invoice_is_never_used_twice() -> None:
    first, second = candidate(invoice_number="INV-1"), candidate(invoice_number="INV-1")
    only_right = candidate(invoice_number="INV-1")

    pairs = match([first, second], [only_right])

    assert [(p.left is not None, p.right is not None) for p in pairs] == [
        (True, True),
        (True, False),
    ]
    assert pairs[1].status == UNMATCHED


def test_a_number_match_is_not_stolen_by_a_looser_match() -> None:
    no_number = candidate(
        invoice_number=None
    )  # would match the right invoice by supplier and total
    with_number = candidate(invoice_number="INV-7")
    right = candidate(invoice_number="INV-7")

    pairs = match([no_number, with_number], [right])

    assert pairs[1].right is right and pairs[0].status == UNMATCHED


def test_unmatched_invoices_on_both_sides_are_listed_with_their_side() -> None:
    left_only, right_only = (
        candidate(invoice_number="L-1"),
        candidate(invoice_number="R-1", total=Decimal("5")),
    )

    pairs = match([left_only], [right_only])

    assert [(p.left is left_only, p.right is right_only, p.status) for p in pairs] == [
        (True, False, UNMATCHED),
        (False, True, UNMATCHED),
    ]


def test_a_different_total_is_reported_with_both_values() -> None:
    (pair,) = match([candidate()], [candidate(total=Decimal("125.00"))])

    assert pair.status == MISMATCH
    assert [(d.field, d.left, d.right) for d in pair.diffs] == [("total", "120.00", "125.00")]


def test_a_rounding_difference_is_not_a_difference() -> None:
    assert compare(candidate().data, candidate(total=Decimal("120.01")).data) == []
    assert [
        d.field for d in compare(candidate().data, candidate(total=Decimal("120.02")).data)
    ] == ["total"]


def test_line_item_count_and_sum_are_compared() -> None:
    other = candidate(line_items=[LineItemData(amount=Decimal("100.00"))])

    assert [d.field for d in compare(candidate().data, other.data)] == ["line_item_count"]
    different_sum = candidate(
        line_items=[LineItemData(amount=Decimal("40")), LineItemData(amount=Decimal("65"))]
    )
    assert [d.field for d in compare(candidate().data, different_sum.data)] == ["line_item_sum"]


def test_date_currency_supplier_and_customer_differences_are_reported() -> None:
    other = candidate(
        invoice_date=date(2026, 1, 6), currency="USD", supplier_name="Initech", customer_name=None
    )

    diffs = {d.field: (d.left, d.right) for d in compare(candidate().data, other.data)}

    assert diffs == {
        "invoice_date": ("2026-01-05", "2026-01-06"),
        "supplier_name": ("Acme Ltd", "Initech"),
        "customer_name": ("Globex", None),
        "currency": ("EUR", "USD"),
    }


def test_the_same_supplier_spelled_differently_is_not_a_difference() -> None:
    assert compare(candidate().data, candidate(supplier_name="ACME LTD.").data) == []
