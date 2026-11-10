import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

DEFAULT_TITLE = "New chat"


class ChatSession(Base):
    """A conversation. No owner: the system has no accounts."""

    __tablename__ = "chat_sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(100), default=DEFAULT_TITLE)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Moved by every saved message; a rename leaves it alone, so it orders the list.
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ChatMessage(Base):
    """One question or one answer. The columns after `content` are set on answers only."""

    __tablename__ = "chat_messages"
    __table_args__ = (Index("ix_chat_messages_session_id_id", "session_id", "id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE")
    )
    role: Mapped[str] = mapped_column(String(10))  # user | assistant
    content: Mapped[str] = mapped_column(Text)
    # The sources as they were sent, not a link: the answer stays readable if a document goes.
    sources: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    citations: Mapped[list[int] | None] = mapped_column(JSONB)
    suggestions: Mapped[list[str] | None] = mapped_column(JSONB)
    rewritten_question: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(String(10))  # done | stopped | failed
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
