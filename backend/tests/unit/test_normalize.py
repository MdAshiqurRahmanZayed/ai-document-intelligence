from datetime import date
from decimal import Decimal

import pytest

from app.normalize.values import normalize_currency, normalize_name, parse_amount, parse_date


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1.234,50", Decimal("1234.50")),
        ("1,234.50", Decimal("1234.50")),
        ("1.234", Decimal("1234")),  # one separator and three digits: thousands
        ("1,234", Decimal("1234")),
        ("12,5", Decimal("12.5")),
        ("0.125", Decimal("0.125")),  # a leading zero cannot start a thousands group
        ("1.234.567", Decimal("1234567")),
        ("1 234,50", Decimal("1234.50")),
        ("(50.00)", Decimal("-50.00")),
        ("-12.30", Decimal("-12.30")),
        ("€ 99", Decimal("99")),
        ("USD 10.00", Decimal("10.00")),
        ("120", Decimal("120")),
    ],
)
def test_amounts_are_read_exactly(text: str, expected: Decimal) -> None:
    assert parse_amount(text) == expected


@pytest.mark.parametrize("text", [None, "", "  ", "n/a", "2026-01-05", "12abc34", "10 - 20"])
def test_unreadable_amounts_are_none(text: str | None) -> None:
    assert parse_amount(text) is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("5 January 2026", date(2026, 1, 5)),
        ("2026-01-05", date(2026, 1, 5)),
        ("05.01.2026", date(2026, 1, 5)),  # day first
        ("05/01/2026", date(2026, 1, 5)),
        ("January 5, 2026", date(2026, 1, 5)),
    ],
)
def test_dates_are_read_day_first_when_ambiguous(text: str, expected: date) -> None:
    assert parse_date(text) == expected


@pytest.mark.parametrize("text", [None, "", "soon", "x" * 50])
def test_unreadable_dates_are_none(text: str | None) -> None:
    assert parse_date(text) is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("€", "EUR"),
        ("$", "USD"),
        ("£", "GBP"),
        ("eur", "EUR"),
        (" usd ", "USD"),
        ("kr", "kr"),  # ambiguous: kept for validation to flag
        (None, None),
        ("", None),
    ],
)
def test_currency_codes(text: str | None, expected: str | None) -> None:
    assert normalize_currency(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Acme Ltd.", "acme"),
        ("ACME LTD", "acme"),
        ("acme limited", "acme"),
        ("Müller GmbH", "müller"),
        ("Smith & Sons, Inc.", "smith sons"),
        ("Ltd", "ltd"),  # a name that is only a company form is kept
        (None, None),
        ("  ", None),
    ],
)
def test_names_compare_equal_across_spellings(text: str | None, expected: str | None) -> None:
    assert normalize_name(text) == expected
