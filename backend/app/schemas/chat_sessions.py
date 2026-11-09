import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_TITLE = 100


def _title(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("title must not be blank")
    return value


class SessionCreate(BaseModel):
    title: str | None = Field(default=None, max_length=MAX_TITLE)

    @field_validator("title")
    @classmethod
    def not_blank(cls, value: str | None) -> str | None:
        return None if value is None else _title(value)


class SessionRename(BaseModel):
    title: str = Field(max_length=MAX_TITLE)

    @field_validator("title")
    @classmethod
    def not_blank(cls, value: str) -> str:
        return _title(value)


class SessionOut(BaseModel):
    id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int


class SessionList(BaseModel):
    items: list[SessionOut]
    total: int


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: Literal["user", "assistant"]
    content: str
    sources: list[dict[str, Any]] | None
    citations: list[int] | None
    suggestions: list[str] | None
    rewritten_question: str | None
    status: Literal["done", "stopped", "failed"] | None
    created_at: datetime


class SessionDetail(SessionOut):
    messages: list[MessageOut]
