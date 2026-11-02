import uuid
from typing import Any

from pydantic import BaseModel

from app.validation.crosscheck import Candidate, Pair


class CrossVerifyRequest(BaseModel):
    left_document_id: uuid.UUID
    right_document_id: uuid.UUID


class DiffOut(BaseModel):
    field: str
    left: str | None
    right: str | None


class InvoiceRefOut(BaseModel):
    extraction_id: uuid.UUID
    data: dict[str, Any]


class CheckOut(BaseModel):
    status: str  # match | mismatch | unmatched
    match_key: str | None
    left: InvoiceRefOut | None  # None when only the right document has this invoice
    right: InvoiceRefOut | None
    diffs: list[DiffOut]


class CrossVerifyResponse(BaseModel):
    checks: list[CheckOut]


def _ref(candidate: Candidate | None) -> InvoiceRefOut | None:
    if candidate is None:
        return None
    return InvoiceRefOut(extraction_id=candidate.extraction_id, data=candidate.data.to_jsonable())


def build_response(pairs: list[Pair]) -> CrossVerifyResponse:
    return CrossVerifyResponse(
        checks=[
            CheckOut(
                status=pair.status,
                match_key=pair.match_key,
                left=_ref(pair.left),
                right=_ref(pair.right),
                diffs=[DiffOut(field=d.field, left=d.left, right=d.right) for d in pair.diffs],
            )
            for pair in pairs
        ]
    )
