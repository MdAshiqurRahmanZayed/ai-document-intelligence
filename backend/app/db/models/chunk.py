import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.types import EMBEDDING_DIM, Vector


class Chunk(Base):
    """A piece of a page's text that search can find."""

    __tablename__ = "chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "page_no", "chunk_no", name="uq_chunks_page_chunk"),
        Index("ix_chunks_document_id", "document_id"),
        # Full-text search. The HNSW index on `embedding` is created by the migration (SQLAlchemy
        # has no portable way to declare it).
        Index("ix_chunks_tsv", "tsv", postgresql_using="gin"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    page_no: Mapped[int] = mapped_column(Integer)
    chunk_no: Mapped[int] = mapped_column(Integer)  # position within the page, from 0
    text: Mapped[str] = mapped_column(Text)
    # Filled by the database from `text`. "simple" means no stemming and no language guess, so
    # words match as written whatever the language of the invoice.
    # deferred: it is only ever used inside SQL (search), so loading a Chunk does not fetch it.
    tsv: Mapped[str | None] = mapped_column(
        TSVECTOR, Computed("to_tsvector('simple', text)", persisted=True), deferred=True
    )
    # NULL until the embedding job has run (or when no Google API key is configured).
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
