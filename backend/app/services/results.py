import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Extraction, ValidationIssue


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
