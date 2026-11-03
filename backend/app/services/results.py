import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Correction, Extraction, ValidationIssue


async def load_results(
    session: AsyncSession, document_id: uuid.UUID
) -> tuple[list[Extraction], list[ValidationIssue]]:
    """The current invoices of a document and all of its findings, in a stable order."""
    extractions = await session.scalars(
        select(Extraction)
        .where(Extraction.document_id == document_id, Extraction.is_current)
        .order_by(Extraction.invoice_index)
    )
    issues = await session.scalars(
        select(ValidationIssue)
        .where(ValidationIssue.document_id == document_id)
        .order_by(ValidationIssue.id)
    )
    return list(extractions), list(issues)


async def load_invoice_issues(
    session: AsyncSession, extraction_id: uuid.UUID
) -> list[ValidationIssue]:
    issues = await session.scalars(
        select(ValidationIssue)
        .where(ValidationIssue.extraction_id == extraction_id)
        .order_by(ValidationIssue.id)
    )
    return list(issues)


async def load_corrections(
    session: AsyncSession, document_id: uuid.UUID
) -> list[tuple[Correction, int]]:
    """The audit trail of a document, newest first, with the invoice each change belongs to."""
    rows = await session.execute(
        select(Correction, Extraction.invoice_index)
        .join(Extraction, Extraction.id == Correction.extraction_id)
        .where(Correction.document_id == document_id)
        .order_by(Correction.created_at.desc(), Correction.id.desc())
    )
    return [(correction, invoice_index) for correction, invoice_index in rows]
