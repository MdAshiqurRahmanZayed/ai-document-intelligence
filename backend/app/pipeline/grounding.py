"""Checks that what the model extracted really appears in the text it was given.

A value the document does not contain was invented, so it is removed (set to None) and reported.
Pure: no database, storage or web imports.
"""

import re
from decimal import Decimal

from rapidfuzz import fuzz

from app.normalize.values import parse_amount
from app.schemas.invoice import AMOUNT_FIELDS, SCALAR_FIELDS, FieldNote, InvoiceDraft, LineItemDraft
from app.validation.findings import WARNING, Finding

# A value counts as present when a stretch of the text matches it at least this well (0 to 100).
# Below 100 on purpose: OCR text often has a wrong letter or two.
MATCH_SCORE = 90
_TOKEN = re.compile(r"\d[\d.,]*")
_SPACE_GROUPED = re.compile(r"\d{1,3}(?: \d{3})+(?:[.,]\d+)?")  # "1 234,50"


def _amounts_in(text: str) -> set[Decimal]:
    """Every number in the text, read the way invoice amounts are read."""
    found = set()
    for token in [*_TOKEN.findall(text), *_SPACE_GROUPED.findall(text)]:
        amount = parse_amount(token.rstrip(".,"))
        if amount is not None:
            found.add(amount)
    return found


def _present(value: str, lowered_text: str) -> bool:
    return fuzz.partial_ratio(value.casefold(), lowered_text) >= MATCH_SCORE


def _is_grounded(
    field: str, value: str, note: FieldNote | None, lowered_text: str, amounts: set[Decimal]
) -> bool:
    if note and note.quote and _present(note.quote, lowered_text):
        return True
    if field in AMOUNT_FIELDS:
        # Compared as numbers, so "1,234.50" in the text grounds "1234.50".
        amount = parse_amount(value)
        return amount is not None and amount in amounts
    return _present(value, lowered_text)


def _line_is_grounded(item: LineItemDraft, lowered_text: str, amounts: set[Decimal]) -> bool:
    if item.description is None and item.amount is None:
        return False  # nothing to check, nothing worth keeping
    if item.description is not None and not _present(item.description, lowered_text):
        return False
    if item.amount is not None:
        amount = parse_amount(item.amount)
        return amount is not None and amount in amounts
    return True


def ground_invoice(draft: InvoiceDraft, text: str) -> tuple[InvoiceDraft, list[Finding]]:
    """Return the draft with every value that is not in `text` removed, and a warning for each."""
    lowered = text.casefold()
    amounts = _amounts_in(text)
    notes = {note.field: note for note in draft.notes}
    findings: list[Finding] = []

    kept: dict[str, str | None] = {}
    for field in SCALAR_FIELDS:
        value: str | None = getattr(draft, field)
        if value is None or not value.strip():
            kept[field] = None
        elif _is_grounded(field, value, notes.get(field), lowered, amounts):
            kept[field] = value
        else:
            kept[field] = None
            message = f"{field} '{value}' is not in the document text, so it was dropped"
            findings.append(Finding("ungrounded_field", WARNING, message, field))

    lines = []
    for item in draft.line_items:
        if _line_is_grounded(item, lowered, amounts):
            lines.append(item)
        else:
            message = "A line item is not in the document text, so it was dropped"
            findings.append(Finding("ungrounded_field", WARNING, message, "line_items"))

    # A note about a removed value would describe something that no longer exists.
    notes_kept = [note for note in draft.notes if kept.get(note.field) is not None]
    grounded = draft.model_copy(update={**kept, "line_items": lines, "notes": notes_kept})
    return grounded, findings
