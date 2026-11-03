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


def invoice_out(extraction: Extraction, issues: Sequence[ValidationIssue]) -> InvoiceOut:
    return InvoiceOut(
        extraction_id=extraction.id,
        invoice_index=extraction.invoice_index,
        version=extraction.version,
        data=extraction.data,
        field_confidence=extraction.field_confidence,
        grounding=extraction.grounding,
        model=extraction.model,
        prompt_version=extraction.prompt_version,
        validation_errors=[IssueOut.model_validate(issue) for issue in issues],
    )


def build_result(
    document: Document, extractions: Sequence[Extraction], issues: Sequence[ValidationIssue]
) -> ResultOut:
    """Current invoices with their findings; findings of earlier versions are left out."""
    by_extraction: dict[uuid.UUID | None, list[ValidationIssue]] = {}
    for issue in issues:
        by_extraction.setdefault(issue.extraction_id, []).append(issue)
    return ResultOut(
        document_id=document.id,
        status=document.status,
        invoices=[invoice_out(e, by_extraction.get(e.id, [])) for e in extractions],
        document_errors=[IssueOut.model_validate(i) for i in by_extraction.get(None, [])],
    )
