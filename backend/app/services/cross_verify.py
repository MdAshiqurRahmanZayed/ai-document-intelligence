import uuid

from sqlalchemy import and_, delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CrossCheck, Document, Extraction
from app.schemas.invoice import InvoiceData
from app.validation.crosscheck import Candidate, Pair, match


class DocumentNotFound(Exception):
    def __init__(self, document_id: uuid.UUID) -> None:
        super().__init__(str(document_id))
        self.document_id = document_id


class NotExtracted(Exception):
    """The document has no current invoices, so there is nothing to compare."""

    def __init__(self, document_id: uuid.UUID) -> None:
        super().__init__(str(document_id))
        self.document_id = document_id


async def _candidates(session: AsyncSession, document_id: uuid.UUID) -> list[Candidate]:
    if await session.get(Document, document_id) is None:
        raise DocumentNotFound(document_id)
    rows = await session.scalars(
        select(Extraction)
        .where(Extraction.document_id == document_id, Extraction.is_current)
        .order_by(Extraction.invoice_index)
    )
    candidates = [Candidate(e.id, InvoiceData.model_validate(e.data)) for e in rows]
    if not candidates:
        raise NotExtracted(document_id)
    return candidates


async def cross_verify(
    session: AsyncSession, left_document_id: uuid.UUID, right_document_id: uuid.UUID
) -> list[Pair]:
    """Compare the invoices of two documents and store the result, replacing the last one."""
    left = await _candidates(session, left_document_id)
    right = await _candidates(session, right_document_id)
    pairs = match(left, right)

    # The earlier result for this pair of documents, whichever side each was on.
    await session.execute(
        delete(CrossCheck).where(
            or_(
                and_(
                    CrossCheck.left_document_id == left_document_id,
                    CrossCheck.right_document_id == right_document_id,
                ),
                and_(
                    CrossCheck.left_document_id == right_document_id,
                    CrossCheck.right_document_id == left_document_id,
                ),
            )
        )
    )
    session.add_all(
        CrossCheck(
            left_document_id=left_document_id,
            right_document_id=right_document_id,
            left_extraction_id=pair.left.extraction_id if pair.left else None,
            right_extraction_id=pair.right.extraction_id if pair.right else None,
            match_key=pair.match_key,
            status=pair.status,
            diffs=[{"field": d.field, "left": d.left, "right": d.right} for d in pair.diffs],
        )
        for pair in pairs
    )
    await session.commit()
    return pairs
