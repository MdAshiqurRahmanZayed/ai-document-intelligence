"""Turns the text a model reads from an invoice into exact, comparable values.

Pure functions: no database, storage or web imports.
"""

import re
from datetime import date
from decimal import Decimal, InvalidOperation

import dateparser

_CURRENCY_SYMBOLS = {"€": "EUR", "$": "USD", "£": "GBP", "৳": "BDT"}
# Written forms that are not ISO codes. "Tk" is the usual short form of the Bangladeshi taka.
_CURRENCY_WORDS = {"tk": "BDT", "tk.": "BDT", "taka": "BDT"}
# Company-form words dropped from the end of a name so "Acme Ltd." and "ACME" compare equal.
_COMPANY_FORMS = {
    "ab", "ag", "as", "bv", "co", "corp", "corporation", "gmbh", "inc", "incorporated",
    "limited", "llc", "ltd", "oy", "plc", "sa", "srl",
}  # fmt: skip
# One number: digits with optional separators and spaces inside ("1 234,50"), no digits elsewhere.
_NUMBER = re.compile(r"\d[\d\s.,]*\d|\d")
_YEAR_FIRST = re.compile(r"\d{4}[-/.]\d{1,2}[-/.]\d{1,2}")


def parse_amount(value: str | None) -> Decimal | None:
    """Read "1.234,50", "1,234.50", "(50.00)" or "EUR 99" as an exact Decimal; None if unreadable.

    With both "." and "," present the last one is the decimal separator. A single separator that
    is followed by exactly three digits is a thousands separator ("1.234" is 1234), unless the
    number starts with 0 ("0.125"); otherwise it is the decimal separator.
    """
    if not value or not value.strip():
        return None
    text = value.strip().replace("−", "-").replace("\xa0", " ")
    negative = text.startswith("-") or (text.startswith("(") and text.endswith(")"))
    chunks = _NUMBER.findall(text)
    if len(chunks) != 1:  # no number, or several (a date, a range, a typo in the middle)
        return None

    digits = chunks[0].replace(" ", "")
    last_dot, last_comma = digits.rfind("."), digits.rfind(",")
    if last_dot >= 0 and last_comma >= 0:
        split = max(last_dot, last_comma)
        whole, fraction = re.sub(r"[.,]", "", digits[:split]), digits[split + 1 :]
    elif last_dot >= 0 or last_comma >= 0:
        separator = "." if last_dot >= 0 else ","
        split = digits.rfind(separator)
        whole, fraction = digits[:split], digits[split + 1 :]
        thousands = digits.count(separator) > 1 or (
            len(fraction) == 3 and not whole.startswith("0")
        )
        if thousands:
            whole, fraction = digits.replace(separator, ""), ""
    else:
        whole, fraction = digits, ""

    try:
        amount = Decimal(f"{whole}.{fraction}" if fraction else whole)
    except InvalidOperation:
        return None
    return -amount if negative else amount


def parse_date(value: str | None) -> date | None:
    """Read a written date as a calendar date; day first when a numeric date is ambiguous."""
    if not value or not value.strip() or len(value) > 40:
        return None
    text = value.strip()
    # A date that starts with a four-digit year (ISO 8601) is year first, never day first.
    order = "YMD" if _YEAR_FIRST.match(text) else "DMY"
    parsed = dateparser.parse(text, settings={"DATE_ORDER": order})
    return parsed.date() if parsed else None


def normalize_currency(value: str | None) -> str | None:
    """Map €, $, £, ৳ and Tk to ISO 4217 codes and upper-case codes; keep anything else as given."""
    if not value or not value.strip():
        return None
    text = value.strip()
    if text in _CURRENCY_SYMBOLS:
        return _CURRENCY_SYMBOLS[text]
    if text.casefold() in _CURRENCY_WORDS:
        return _CURRENCY_WORDS[text.casefold()]
    # Not forced to a valid code: validation reports an unknown currency instead of hiding it.
    return text.upper() if text.isalpha() and len(text) == 3 else text


def normalize_name(value: str | None) -> str | None:
    """Lower-case a company name, drop punctuation and trailing company-form words."""
    if not value:
        return None
    words = re.sub(r"[^\w\s]", " ", value.casefold()).split()
    while len(words) > 1 and words[-1] in _COMPANY_FORMS:
        words.pop()
    return " ".join(words) or None
