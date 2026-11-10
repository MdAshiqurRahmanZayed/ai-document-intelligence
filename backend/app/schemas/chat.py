import uuid
from typing import Literal

from pydantic import BaseModel, Field, field_validator

MAX_QUESTION_CHARS = 1000
MAX_MESSAGE_CHARS = 2000
MAX_HISTORY = 6  # the last three turns


class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=MAX_MESSAGE_CHARS)


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=MAX_QUESTION_CHARS)
    history: list[HistoryMessage] = Field(default_factory=list, max_length=MAX_HISTORY)
    # With a session the question and answer are saved and the stored messages replace `history`.
    session_id: uuid.UUID | None = None

    @field_validator("question")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("question must not be blank")
        return value.strip()
