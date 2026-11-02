"""create extractions, validation_errors and cross_checks

Revision ID: 0002
Revises: 0001
"""

from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def _created_at() -> sa.Column[Any]:
    return sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        server_default=sa.text("now()"),
        nullable=False,
    )


def upgrade() -> None:
    op.create_table(
        "extractions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("invoice_index", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("data", postgresql.JSONB(), nullable=False),
        sa.Column("field_confidence", postgresql.JSONB(), nullable=False),
        sa.Column("grounding", postgresql.JSONB(), nullable=False),
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("prompt_version", sa.String(20), nullable=False),
        _created_at(),
        sa.Column("invoice_number", sa.String(100), nullable=True),
        sa.Column("supplier_norm", sa.String(255), nullable=True),
        sa.Column("invoice_date", sa.Date(), nullable=True),
        sa.Column("total", sa.Numeric(18, 4), nullable=True),
        sa.Column("currency", sa.String(10), nullable=True),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_extractions_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_extractions")),
        sa.UniqueConstraint(
            "document_id",
            "invoice_index",
            "version",
            name="uq_extractions_document_id_invoice_index_version",
        ),
    )
    op.create_index(
        "ix_extractions_supplier_norm_invoice_number",
        "extractions",
        ["supplier_norm", "invoice_number"],
    )
    op.create_index(
        "ix_extractions_document_id_is_current", "extractions", ["document_id", "is_current"]
    )

    op.create_table(
        "validation_errors",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("extraction_id", sa.Uuid(), nullable=True),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("field", sa.String(50), nullable=True),
        sa.Column("severity", sa.String(10), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("related_document_id", sa.Uuid(), nullable=True),
        _created_at(),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_validation_errors_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["extraction_id"],
            ["extractions.id"],
            name=op.f("fk_validation_errors_extraction_id_extractions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["related_document_id"],
            ["documents.id"],
            name=op.f("fk_validation_errors_related_document_id_documents"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_validation_errors")),
    )

    op.create_table(
        "cross_checks",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("left_document_id", sa.Uuid(), nullable=False),
        sa.Column("right_document_id", sa.Uuid(), nullable=False),
        sa.Column("left_extraction_id", sa.Uuid(), nullable=True),
        sa.Column("right_extraction_id", sa.Uuid(), nullable=True),
        sa.Column("match_key", sa.String(255), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("diffs", postgresql.JSONB(), nullable=False),
        _created_at(),
        sa.ForeignKeyConstraint(
            ["left_document_id"],
            ["documents.id"],
            name=op.f("fk_cross_checks_left_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["right_document_id"],
            ["documents.id"],
            name=op.f("fk_cross_checks_right_document_id_documents"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["left_extraction_id"],
            ["extractions.id"],
            name=op.f("fk_cross_checks_left_extraction_id_extractions"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["right_extraction_id"],
            ["extractions.id"],
            name=op.f("fk_cross_checks_right_extraction_id_extractions"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cross_checks")),
    )
    op.create_index(
        "ix_cross_checks_left_document_id_right_document_id",
        "cross_checks",
        ["left_document_id", "right_document_id"],
    )


def downgrade() -> None:
    op.drop_table("cross_checks")
    op.drop_table("validation_errors")
    op.drop_table("extractions")
