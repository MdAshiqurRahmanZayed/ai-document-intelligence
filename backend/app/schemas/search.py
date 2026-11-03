import uuid

from pydantic import BaseModel

from app.schemas.listing import InvoiceSummaryOut, invoice_summary_out
from app.services.search import Mode, SearchOutcome


class SearchResultOut(BaseModel):
    document_id: uuid.UUID
    filename: str
    status: str
    page_no: int
    snippet: str  # HTML-safe: document text is escaped, matches are wrapped in <mark>
    score: float
    invoices: list[InvoiceSummaryOut]


class SearchOut(BaseModel):
    mode_used: Mode
    results: list[SearchResultOut]


def build_search(outcome: SearchOutcome) -> SearchOut:
    return SearchOut(
        mode_used=outcome.mode_used,
        results=[
            SearchResultOut(
                document_id=r.document.id,
                filename=r.document.filename,
                status=r.document.status,
                page_no=r.page_no,
                snippet=r.snippet,
                score=r.score,
                invoices=[invoice_summary_out(s) for s in r.invoices],
            )
            for r in outcome.results
        ],
    )
