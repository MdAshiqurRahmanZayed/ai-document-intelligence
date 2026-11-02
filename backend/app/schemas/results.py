import uuid
from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.db.models import Document, Extraction, ValidationIssue


class IssueOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    field: str | None
    severity: str
    message: str
    related_document_id: uuid.UUID | None


class InvoiceOut(BaseModel):
    extraction_id: uuid.UUID
    invoice_index: int
    version: int
    data: dict[str, Any]
    field_confidence: dict[str, float]
    grounding: dict[str, str]  # field -> the quote it was read from
    model: str
    prompt_version: str
    validation_errors: list[IssueOut]


class ResultOut(BaseModel):
    document_id: uuid.UUID
    status: str
    invoices: list[InvoiceOut]
    document_errors: list[IssueOut]  # findings about the whole document, e.g. no invoice found


def build_result(
    document: Document, extractions: Sequence[Extraction], issues: Sequence[ValidationIssue]
) -> ResultOut:
    """Current invoices with their findings; findings of earlier versions are left out."""
    by_extraction: dict[uuid.UUID | None, list[IssueOut]] = {}
    for issue in issues:
        by_extraction.setdefault(issue.extraction_id, []).append(IssueOut.model_validate(issue))
    return ResultOut(
        document_id=document.id,
        status=document.status,
        invoices=[
            InvoiceOut(
                extraction_id=e.id,
                invoice_index=e.invoice_index,
                version=e.version,
                data=e.data,
                field_confidence=e.field_confidence,
                grounding=e.grounding,
                model=e.model,
                prompt_version=e.prompt_version,
                validation_errors=by_extraction.get(e.id, []),
            )
            for e in extractions
        ],
        document_errors=by_extraction.get(None, []),
    )
