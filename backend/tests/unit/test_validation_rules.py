from collections.abc import Mapping
from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from app.db.models.document import DocumentStatus
from app.schemas.invoice import InvoiceData, LineItemData
from app.validation.findings import ERROR, WARNING, Finding
from app.validation.rules import REQUIRED_FIELDS, route, validate_invoice

TODAY = date(2026, 6, 1)


def line(amount: str, quantity: str | None = None, unit_price: str | None = None) -> LineItemData:
    return LineItemData(
        description="item",
        quantity=Decimal(quantity) if quantity else None,
        unit_price=Decimal(unit_price) if unit_price else None,
        amount=Decimal(amount),
    )


def invoice(**overrides: Any) -> InvoiceData:
    """A consistent invoice: 40 + 60 = 100, plus 20 tax = 120."""
    fields: dict[str, Any] = {
        "invoice_number": "INV-1",
        "invoice_date": date(2026, 1, 5),
        "supplier_name": "Acme Ltd",
        "customer_name": "Globex",
        "subtotal": Decimal("100.00"),
        "tax": Decimal("20.00"),
        "total": Decimal("120.00"),
        "currency": "EUR",
        "line_items": [line("40.00"), line("60.00")],
    }
    fields.update(overrides)
    return InvoiceData(**fields)


def run(data: InvoiceData, confidence: Mapping[str, float] | None = None) -> list[Finding]:
    return validate_invoice(data, confidence or {}, TODAY, threshold=0.5)


def codes(findings: list[Finding]) -> set[tuple[str, str | None]]:
    return {(f.code, f.field) for f in findings}


def test_a_consistent_invoice_has_no_findings() -> None:
    assert run(invoice()) == []


@pytest.mark.parametrize("field", REQUIRED_FIELDS)
def test_each_required_field_is_reported_when_missing(field: str) -> None:
    findings = run(invoice(**{field: None}))

    assert ("missing_field", field) in codes(findings)
    assert all(f.severity == ERROR for f in findings if f.code == "missing_field")


def test_customer_name_is_not_required() -> None:
    assert ("missing_field", "customer_name") not in codes(run(invoice(customer_name=None)))


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"total": Decimal("-50.00"), "subtotal": None, "tax": None}, "total"),
        ({"tax": Decimal("-1.00"), "total": Decimal("99.00")}, "tax"),
        (
            {"line_items": [LineItemData(quantity=Decimal("-1"))], "subtotal": None},
            "line_items[0].quantity",
        ),
        ({"line_items": [line("-5.00")], "subtotal": None}, "line_items[0].amount"),
    ],
)
def test_negative_amounts_are_errors(overrides: dict[str, Any], field: str) -> None:
    assert ("negative_amount", field) in codes(run(invoice(**overrides)))


def test_an_absurdly_large_amount_is_an_error() -> None:
    findings = run(invoice(total=Decimal("2000000000000"), subtotal=None, tax=None))

    assert ("implausible_amount", "total") in codes(findings)


def test_a_line_amount_that_is_not_quantity_times_price_is_a_warning() -> None:
    bad = invoice(line_items=[line("35.00", "3", "10.00")], subtotal=None, tax=None)
    good = invoice(line_items=[line("30.00", "3", "10.00")], subtotal=None, tax=None)

    assert ("line_amount_mismatch", "line_items[0].amount") in codes(run(bad))
    assert next(f for f in run(bad) if f.code == "line_amount_mismatch").severity == WARNING
    assert "line_amount_mismatch" not in {f.code for f in run(good)}


@pytest.mark.parametrize(
    ("line_amounts", "expected"),
    [
        (["40.00", "50.00"], True),  # adds up to 90, subtotal is 100
        (["40.00", "60.00"], False),
        (["50.50", "50.00"], False),  # 100.50: exactly on the 0.5 percent tolerance
        (["50.51", "50.00"], True),  # 100.51: just beyond it
    ],
)
def test_line_items_must_add_up_to_the_subtotal(line_amounts: list[str], expected: bool) -> None:
    data = invoice(line_items=[line(a) for a in line_amounts], tax=None, total=None)

    assert (("line_items_sum_mismatch", "subtotal") in codes(run(data))) is expected


def test_a_line_without_an_amount_makes_the_sum_incomplete_so_it_is_not_checked() -> None:
    data = invoice(
        line_items=[line("40.00"), LineItemData(description="gift")], tax=None, total=None
    )

    assert "line_items_sum_mismatch" not in {f.code for f in run(data)}


@pytest.mark.parametrize(
    ("total", "expected"),
    [("130.00", True), ("120.00", False), ("120.50", False), ("120.51", True)],
)
def test_subtotal_plus_tax_must_equal_the_total(total: str, expected: bool) -> None:
    data = invoice(total=Decimal(total))

    assert (("total_mismatch", "total") in codes(run(data))) is expected


def test_missing_parts_give_no_totals_finding() -> None:
    data = invoice(subtotal=None, tax=None, line_items=[])

    assert {f.code for f in run(data)} == set()


@pytest.mark.parametrize(("tax", "expected"), [("50.00", True), ("30.00", False), ("0.00", False)])
def test_an_implausible_tax_rate_is_a_warning(tax: str, expected: bool) -> None:
    data = invoice(tax=Decimal(tax), total=Decimal("100.00") + Decimal(tax), line_items=[])

    assert (("implausible_tax_rate", "tax") in codes(run(data))) is expected


@pytest.mark.parametrize(
    ("invoice_date", "code", "severity"),
    [
        (date(2027, 6, 1), "future_date", ERROR),
        (date(1999, 12, 31), "old_date", WARNING),
    ],
)
def test_dates_outside_the_plausible_range_are_flagged(
    invoice_date: date, code: str, severity: str
) -> None:
    findings = run(invoice(invoice_date=invoice_date))

    assert [(f.code, f.severity) for f in findings] == [(code, severity)]


@pytest.mark.parametrize("invoice_date", [TODAY, date(2000, 1, 1)])
def test_today_and_the_oldest_accepted_date_are_fine(invoice_date: date) -> None:
    assert run(invoice(invoice_date=invoice_date)) == []


@pytest.mark.parametrize(
    ("currency", "code", "severity"),
    [
        (None, "missing_currency", WARNING),
        ("ZZZ", "invalid_currency", ERROR),
        ("kr", "invalid_currency", ERROR),
    ],
)
def test_currency_must_be_present_and_an_iso_code(
    currency: str | None, code: str, severity: str
) -> None:
    findings = run(invoice(currency=currency))

    assert [(f.code, f.severity) for f in findings] == [(code, severity)]


def test_low_confidence_is_a_warning_only_below_the_threshold_for_filled_fields() -> None:
    data = invoice(customer_name=None)
    confidence = {"supplier_name": 0.3, "total": 0.5, "invoice_number": 0.49, "customer_name": 0.1}

    findings = run(data, confidence)

    # 0.5 is not below the threshold, and an empty field has nothing to be unsure about.
    assert codes([f for f in findings if f.code == "low_confidence"]) == {
        ("low_confidence", "supplier_name"),
        ("low_confidence", "invoice_number"),
    }


def test_a_field_without_a_confidence_is_not_flagged() -> None:
    assert run(invoice(), {}) == []


def warning(code: str) -> Finding:
    return Finding(code, WARNING, "m")


@pytest.mark.parametrize(
    ("findings", "has_invoices", "status"),
    [
        ([], True, DocumentStatus.COMPLETED),
        ([Finding("total_mismatch", ERROR, "m")], True, DocumentStatus.NEEDS_REVIEW),
        ([warning("old_date"), warning("ungrounded_field")], True, DocumentStatus.COMPLETED),
        ([warning("low_confidence")], True, DocumentStatus.NEEDS_REVIEW),
        ([], False, DocumentStatus.NEEDS_REVIEW),
    ],
)
def test_routing_sends_a_document_for_review_only_when_needed(
    findings: list[Finding], has_invoices: bool, status: str
) -> None:
    assert route(findings, has_invoices) == status
