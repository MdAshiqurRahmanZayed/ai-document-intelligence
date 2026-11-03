from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.db.models import Correction


class CorrectionRequest(BaseModel):
    # Values are checked and normalized by the service, which knows the editable fields.
    fields: dict[str, Any]
    edited_by: str | None = Field(default=None, max_length=100)


class CorrectionOut(BaseModel):
    invoice_index: int
    field: str
    old_value: str | None
    new_value: str | None
    edited_by: str
    created_at: datetime


class CorrectionsOut(BaseModel):
    corrections: list[CorrectionOut]


def build_corrections(rows: list[tuple[Correction, int]]) -> CorrectionsOut:
    return CorrectionsOut(
        corrections=[
            CorrectionOut(
                invoice_index=invoice_index,
                field=c.field,
                old_value=c.old_value,
                new_value=c.new_value,
                edited_by=c.edited_by,
                created_at=c.created_at,
            )
            for c, invoice_index in rows
        ]
    )
