import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Extraction(Base):
    """One invoice read from a document by one extraction run (a version)."""

    __tablename__ = "extractions"
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "invoice_index",
            "version",
            name="uq_extractions_document_id_invoice_index_version",
        ),
        # Duplicate detection looks invoices up by supplier and number.
        Index("ix_extractions_supplier_norm_invoice_number", "supplier_norm", "invoice_number"),
        Index("ix_extractions_document_id_is_current", "document_id", "is_current"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    invoice_index: Mapped[int] = mapped_column(Integer)  # position of the invoice in the document
    version: Mapped[int] = mapped_column(Integer)  # one per extraction run
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    # The normalized invoice, amounts as strings so no binary float is ever involved.
    data: Mapped[dict[str, Any]] = mapped_column(JSONB)
    field_confidence: Mapped[dict[str, float]] = mapped_column(JSONB)  # field -> 0 to 1
    grounding: Mapped[dict[str, str]] = mapped_column(JSONB)  # field -> quote it came from
    model: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Copies of key fields from `data`, kept as columns so lookups can use indexes.
    invoice_number: Mapped[str | None] = mapped_column(String(100))
    supplier_norm: Mapped[str | None] = mapped_column(String(255))
    invoice_date: Mapped[date | None] = mapped_column(Date)
    total: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    currency: Mapped[str | None] = mapped_column(String(10))


class ValidationIssue(Base):
    """A validation finding. Document-level findings have no extraction."""

    __tablename__ = "validation_errors"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    extraction_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("extractions.id", ondelete="CASCADE")
    )
    code: Mapped[str] = mapped_column(String(50))
    field: Mapped[str | None] = mapped_column(String(50))
    severity: Mapped[str] = mapped_column(String(10))  # error | warning
    message: Mapped[str] = mapped_column(Text)
    # The other document, for duplicate findings.
    related_document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CrossCheck(Base):
    """The comparison of one invoice of the left document with one of the right document."""

    __tablename__ = "cross_checks"
    __table_args__ = (
        Index(
            "ix_cross_checks_left_document_id_right_document_id",
            "left_document_id",
            "right_document_id",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    left_document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE")
    )
    right_document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE")
    )
    # Null on the side that has no matching invoice.
    left_extraction_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("extractions.id", ondelete="SET NULL")
    )
    right_extraction_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("extractions.id", ondelete="SET NULL")
    )
    match_key: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20))  # match | mismatch | unmatched
    diffs: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)  # [{field, left, right}]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
