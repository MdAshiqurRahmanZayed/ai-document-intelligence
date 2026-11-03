import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel

from app.services.listing import DocumentPage, DocumentRow, InvoiceSummary


class InvoiceSummaryOut(BaseModel):
    invoice_index: int
    invoice_number: str | None
    supplier_name: str | None
    invoice_date: date | None
    total: Decimal | None
    currency: str | None


class DocumentSummaryOut(BaseModel):
    id: uuid.UUID
    filename: str
    status: str
    source_type: str
    page_count: int | None
    error_code: str | None
    created_at: datetime
    updated_at: datetime
    invoices: list[InvoiceSummaryOut]


class DocumentListOut(BaseModel):
    items: list[DocumentSummaryOut]
    next_cursor: str | None


class FileLinkOut(BaseModel):
    url: str
    expires_in: int


def invoice_summary_out(summary: InvoiceSummary) -> InvoiceSummaryOut:
    return InvoiceSummaryOut(
        invoice_index=summary.invoice_index,
        invoice_number=summary.invoice_number,
        supplier_name=summary.supplier_name,
        invoice_date=summary.invoice_date,
        total=summary.total,
        currency=summary.currency,
    )


def document_summary_out(row: DocumentRow) -> DocumentSummaryOut:
    d = row.document
    return DocumentSummaryOut(
        id=d.id,
        filename=d.filename,
        status=d.status,
        source_type=d.source_type,
        page_count=d.page_count,
        error_code=d.error_code,
        created_at=d.created_at,
        updated_at=d.updated_at,
        invoices=[invoice_summary_out(s) for s in row.invoices],
    )


def build_list(page: DocumentPage) -> DocumentListOut:
    return DocumentListOut(
        items=[document_summary_out(row) for row in page.items], next_cursor=page.next_cursor
    )
