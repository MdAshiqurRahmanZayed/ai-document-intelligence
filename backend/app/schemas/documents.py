import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class UploadItem(BaseModel):
    filename: str
    status: Literal["accepted", "duplicate", "rejected"]
    document_id: uuid.UUID | None = None
    reason: str | None = None


class UploadResponse(BaseModel):
    results: list[UploadItem]


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    stage: str
    status: str
    duration_ms: int | None
    error_code: str | None
    error_message: str | None
    attempt: int
    created_at: datetime


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    mime: str
    size: int
    status: str
    source_type: str
    page_count: int | None
    error_code: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
    events: list[EventOut]
