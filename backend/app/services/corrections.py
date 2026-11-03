"""Manual corrections of an extracted invoice: a new version, an audit trail, re-validation."""

import json
import uuid
from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Correction, Document, DocumentStatus, Extraction
from app.normalize.invoice import normalize_invoice
from app.schemas.invoice import SCALAR_FIELDS, InvoiceData, InvoiceDraft, LineItemDraft
from app.services.errors import DocumentNotFound
from app.services.extraction import (
    ExtractedRecord,
    document_status,
    lookup_columns,
    validate_invoice_findings,
)

EDITABLE_FIELDS = (*SCALAR_FIELDS, "line_items")
LINE_FIELDS = ("description", "quantity", "unit_price", "amount")
# While a job is working on the document its results are about to change under the editor.
BUSY_STATUSES = (DocumentStatus.UPLOADED, DocumentStatus.QUEUED, DocumentStatus.PROCESSING)
MANUAL = "manual"


class InvoiceNotFound(Exception):
    pass


class DocumentBusy(Exception):
    pass


class InvalidCorrection(Exception):
    """The request cannot be applied. `field` names what is wrong."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field
        self.message = message


def _text(value: object) -> str | None:
    """A value as the string the normalizer reads; None stays None."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, str | int | float):
        raise TypeError(f"expected text or a number, got {type(value).__name__}")
    return str(value)


def _draft_from(data: InvoiceData) -> InvoiceDraft:
    """The stored invoice as the text values a draft holds, so a patch can be laid over it."""

    def number(value: Any) -> str | None:
        return None if value is None else format(value, "f")  # fixed point, never "1E+2"

    return InvoiceDraft(
        invoice_number=data.invoice_number,
        invoice_date=None if data.invoice_date is None else data.invoice_date.isoformat(),
        supplier_name=data.supplier_name,
        customer_name=data.customer_name,
        subtotal=number(data.subtotal),
        tax=number(data.tax),
        total=number(data.total),
        currency=data.currency,
        line_items=[
            LineItemDraft(
                description=line.description,
                quantity=number(line.quantity),
                unit_price=number(line.unit_price),
                amount=number(line.amount),
            )
            for line in data.line_items
        ],
    )


def _apply_patch(draft: InvoiceDraft, fields: Mapping[str, Any]) -> InvoiceDraft:
    unknown = sorted(set(fields) - set(EDITABLE_FIELDS))
    if unknown:
        raise InvalidCorrection(unknown[0], f"{unknown[0]} cannot be edited")
    changes: dict[str, Any] = {}
    for field in SCALAR_FIELDS:
        if field in fields:
            try:
                changes[field] = _text(fields[field])
            except TypeError as exc:
                raise InvalidCorrection(field, str(exc)) from exc
    if "line_items" in fields:
        changes["line_items"] = _line_drafts(fields["line_items"])
    return draft.model_copy(update=changes)


def _line_drafts(value: Any) -> list[LineItemDraft]:
    if not isinstance(value, Sequence) or isinstance(value, str):
        raise InvalidCorrection("line_items", "line_items must be a list")
    lines = []
    for position, item in enumerate(value):
        if not isinstance(item, Mapping) or set(item) - set(LINE_FIELDS):
            raise InvalidCorrection(
                f"line_items[{position}]", f"a line item has only {', '.join(LINE_FIELDS)}"
            )
        try:
            lines.append(LineItemDraft(**{name: _text(item.get(name)) for name in LINE_FIELDS}))
        except TypeError as exc:
            raise InvalidCorrection(f"line_items[{position}]", str(exc)) from exc
    return lines


def _audit_text(field: str, data: InvoiceData) -> str | None:
    """A field's value as stored in the audit trail: text, JSON for line items, None if empty."""
    value = getattr(data, field)
    if field == "line_items":
        return json.dumps(data.to_jsonable()["line_items"]) if value else None
    if value is None:
        return None
    return value.isoformat() if isinstance(value, date) else str(value)


def _changed_fields(before: InvoiceData, after: InvoiceData) -> list[str]:
    return [f for f in EDITABLE_FIELDS if getattr(before, f) != getattr(after, f)]


async def correct_invoice(
    session: AsyncSession,
    document_id: uuid.UUID,
    invoice_index: int,
    fields: Mapping[str, Any],
    edited_by: str,
    today: date,
    threshold: float,
) -> Extraction:
    """Apply a patch to one invoice and return its (new, or unchanged) current version."""
    document = await session.get(Document, document_id)
    if document is None:
        raise DocumentNotFound(document_id)
    if document.status in BUSY_STATUSES:
        raise DocumentBusy
    # FOR UPDATE: two edits of the same invoice at once must not both make "version 2".
    current = await session.scalar(
        select(Extraction)
        .where(
            Extraction.document_id == document_id,
            Extraction.invoice_index == invoice_index,
            Extraction.is_current,
        )
        .with_for_update()
    )
    if current is None:
        raise InvoiceNotFound

    before = InvoiceData.model_validate(current.data)
    patched = _apply_patch(_draft_from(before), fields)
    # A person's value is authoritative, so it is normalized but not grounded in the text.
    after, unreadable = normalize_invoice(patched)
    bad = [f for f in unreadable if f.field is not None and f.field.split("[")[0] in fields]
    if bad:
        raise InvalidCorrection(bad[0].field or "fields", bad[0].message)
    changed = _changed_fields(before, after)
    if not changed:
        await session.commit()  # nothing was written; this only releases the row lock
        return current

    latest = await session.scalar(
        select(func.max(Extraction.version)).where(
            Extraction.document_id == document_id, Extraction.invoice_index == invoice_index
        )
    )
    await session.execute(
        update(Extraction).where(Extraction.id == current.id).values(is_current=False)
    )
    edited = set(changed)
    # Values the person did not touch keep their confidence; values they set are trusted fully.
    confidence = {
        f: score
        for f, score in current.field_confidence.items()
        if f not in edited and getattr(after, f) is not None
    }
    confidence.update(
        {f: 1.0 for f in edited if f in SCALAR_FIELDS and getattr(after, f) is not None}
    )
    new = Extraction(
        document_id=document_id,
        invoice_index=invoice_index,
        version=(latest or 0) + 1,
        is_current=True,
        data=after.to_jsonable(),
        field_confidence=confidence,
        grounding={f: q for f, q in current.grounding.items() if f not in edited},
        model=MANUAL,
        prompt_version=MANUAL,
        **lookup_columns(after),
    )
    session.add(new)
    await session.flush()  # the new row's id is needed below
    session.add_all(
        Correction(
            document_id=document_id,
            extraction_id=new.id,
            field=field,
            old_value=_audit_text(field, before),
            new_value=_audit_text(field, after),
            edited_by=edited_by,
        )
        for field in changed
    )
    await validate_invoice_findings(
        session,
        document_id,
        ExtractedRecord(new, after, confidence, unreadable),
        today,
        threshold,
    )
    document.status = await document_status(session, document_id)
    await session.commit()
    return new
