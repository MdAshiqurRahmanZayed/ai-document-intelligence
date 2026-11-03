"""Listing and filtering documents, shared by the list endpoint and by search."""

import base64
import binascii
import json
import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import ColumnElement, exists, func, literal, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, Extraction
from app.normalize.values import normalize_name


class InvalidCursor(Exception):
    pass


@dataclass(frozen=True)
class DocumentFilters:
    status: str | None = None
    # Invoice filters: a document matches when ONE current invoice satisfies all of them.
    supplier: str | None = None
    invoice_number: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    amount_min: Decimal | None = None
    amount_max: Decimal | None = None
    currency: str | None = None


@dataclass(frozen=True)
class InvoiceSummary:
    invoice_index: int
    invoice_number: str | None
    supplier_name: str | None
    invoice_date: date | None
    total: Decimal | None
    currency: str | None


@dataclass(frozen=True)
class DocumentRow:
    document: Document
    invoices: list[InvoiceSummary]


@dataclass(frozen=True)
class DocumentPage:
    items: list[DocumentRow]
    next_cursor: str | None


def _like_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _invoice_conditions(f: DocumentFilters) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = []
    supplier = normalize_name(f.supplier)
    if supplier:  # same normalization as the stored `supplier_norm`
        conditions.append(Extraction.supplier_norm.like(f"%{_like_escape(supplier)}%", escape="\\"))
    number = re.sub(r"[^0-9a-z]", "", (f.invoice_number or "").casefold())
    if number:  # compared without case, spaces or punctuation, like cross-verification does
        stored = func.regexp_replace(func.lower(Extraction.invoice_number), "[^0-9a-z]", "", "g")
        conditions.append(stored == number)
    if f.date_from is not None:
        conditions.append(Extraction.invoice_date >= f.date_from)
    if f.date_to is not None:
        conditions.append(Extraction.invoice_date <= f.date_to)
    if f.amount_min is not None:
        conditions.append(Extraction.total >= f.amount_min)
    if f.amount_max is not None:
        conditions.append(Extraction.total <= f.amount_max)
    if f.currency and f.currency.strip():
        conditions.append(func.upper(Extraction.currency) == f.currency.strip().upper())
    return conditions


def document_conditions(f: DocumentFilters) -> list[ColumnElement[bool]]:
    """WHERE conditions on `documents` for the filters (empty when no filter is set)."""
    conditions: list[ColumnElement[bool]] = []
    if f.status:
        conditions.append(Document.status == f.status)
    invoice = _invoice_conditions(f)
    if invoice:
        conditions.append(
            exists().where(Extraction.document_id == Document.id, Extraction.is_current, *invoice)
        )
    return conditions


def encode_cursor(created_at: datetime, document_id: uuid.UUID) -> str:
    raw = json.dumps([created_at.isoformat(), str(document_id)]).encode()
    return base64.urlsafe_b64encode(raw).decode()


def decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        created_at, document_id = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        return datetime.fromisoformat(created_at), uuid.UUID(document_id)
    except (binascii.Error, ValueError, TypeError, KeyError) as exc:
        raise InvalidCursor from exc


async def invoice_summaries(
    session: AsyncSession, document_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[InvoiceSummary]]:
    """The current invoices of the given documents, in invoice order."""
    summaries: dict[uuid.UUID, list[InvoiceSummary]] = {}
    if not document_ids:
        return summaries
    rows = await session.scalars(
        select(Extraction)
        .where(Extraction.document_id.in_(document_ids), Extraction.is_current)
        .order_by(Extraction.document_id, Extraction.invoice_index)
    )
    for e in rows:
        summaries.setdefault(e.document_id, []).append(
            InvoiceSummary(
                invoice_index=e.invoice_index,
                invoice_number=e.invoice_number,
                supplier_name=e.data.get("supplier_name"),
                invoice_date=e.invoice_date,
                total=e.total,
                currency=e.currency,
            )
        )
    return summaries


async def list_documents(
    session: AsyncSession, filters: DocumentFilters, limit: int, cursor: str | None
) -> DocumentPage:
    """Newest first. Keyset pagination: a cursor names the last row seen, so a page does not
    shift when new documents arrive (offsets would)."""
    query = (
        select(Document)
        .where(*document_conditions(filters))
        .order_by(Document.created_at.desc(), Document.id.desc())
        .limit(limit + 1)  # one extra row tells whether a next page exists
    )
    if cursor is not None:
        created_at, document_id = decode_cursor(cursor)
        # Typed like the columns: a bare datetime would be sent as "timestamp without time zone".
        after = tuple_(
            literal(created_at, Document.created_at.type), literal(document_id, Document.id.type)
        )
        query = query.where(tuple_(Document.created_at, Document.id) < after)
    rows = list(await session.scalars(query))
    has_next = len(rows) > limit
    rows = rows[:limit]
    summaries = await invoice_summaries(session, [d.id for d in rows])
    return DocumentPage(
        items=[DocumentRow(d, summaries.get(d.id, [])) for d in rows],
        next_cursor=encode_cursor(rows[-1].created_at, rows[-1].id) if has_next else None,
    )
