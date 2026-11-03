"""Helpers that put documents with invoices into the test database."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, DocumentStatus, Extraction
from app.normalize.values import normalize_name
from tests.helpers import make_document

BASE = datetime(2026, 1, 1, tzinfo=UTC)


async def add_document(
    session: AsyncSession, minutes: int = 0, status: str = DocumentStatus.COMPLETED
) -> Document:
    """A document created `minutes` after BASE, so the order of creation is under control."""
    document = make_document(created_at=BASE + timedelta(minutes=minutes), status=status)
    session.add(document)
    await session.commit()
    return document


async def add_invoice(
    session: AsyncSession,
    document: Document,
    *,
    index: int = 0,
    version: int = 1,
    current: bool = True,
    number: str | None = "INV-1",
    supplier: str | None = "Acme Industries Ltd.",
    on: date | None = date(2026, 1, 5),
    total: str | None = "120.00",
    currency: str | None = "EUR",
) -> Extraction:
    extraction = Extraction(
        document_id=document.id,
        invoice_index=index,
        version=version,
        is_current=current,
        data={"invoice_number": number, "supplier_name": supplier},
        field_confidence={},
        grounding={},
        model="test-model",
        prompt_version="v1",
        invoice_number=number,
        supplier_norm=normalize_name(supplier),
        invoice_date=on,
        total=None if total is None else Decimal(total),
        currency=currency,
    )
    session.add(extraction)
    await session.commit()
    return extraction
