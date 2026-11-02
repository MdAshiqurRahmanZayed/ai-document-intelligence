from decimal import Decimal

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    CrossCheck,
    Document,
    DocumentStatus,
    Extraction,
    Page,
    ProcessingEvent,
    ValidationIssue,
)
from tests.helpers import make_document


async def test_new_document_defaults(session: AsyncSession) -> None:
    document = make_document()
    session.add(document)
    await session.commit()
    await session.refresh(document)

    assert document.status == DocumentStatus.UPLOADED
    assert document.created_at is not None


async def test_sha256_must_be_unique(session: AsyncSession) -> None:
    session.add(make_document(sha256="a" * 64))
    session.add(make_document(sha256="a" * 64))
    with pytest.raises(IntegrityError):
        await session.commit()


async def test_page_number_is_unique_per_document(session: AsyncSession) -> None:
    document = make_document()
    session.add(document)
    await session.commit()

    session.add_all(
        [Page(document_id=document.id, page_no=1), Page(document_id=document.id, page_no=1)]
    )
    with pytest.raises(IntegrityError):
        await session.commit()


async def test_deleting_a_document_removes_its_pages_and_events(session: AsyncSession) -> None:
    document = make_document()
    session.add(document)
    await session.commit()
    session.add(Page(document_id=document.id, page_no=1))
    session.add(
        ProcessingEvent(document_id=document.id, stage="ingest", status="started", attempt=1)
    )
    await session.commit()

    await session.execute(delete(Document))
    await session.commit()

    for model in (Page, ProcessingEvent):
        assert await session.scalar(select(func.count()).select_from(model)) == 0


def make_extraction(document: Document, **overrides: object) -> Extraction:
    fields: dict[str, object] = {
        "document_id": document.id,
        "invoice_index": 0,
        "version": 1,
        "data": {"invoice_number": "INV-1", "total": "120.50"},
        "field_confidence": {"invoice_number": 0.9},
        "grounding": {"invoice_number": "Invoice INV-1"},
        "model": "test-model",
        "prompt_version": "v1",
    }
    fields.update(overrides)
    return Extraction(**fields)


async def test_extraction_findings_and_cross_check_round_trip(session: AsyncSession) -> None:
    left, right = make_document(), make_document()
    session.add_all([left, right])
    await session.commit()
    extraction = make_extraction(left, invoice_number="INV-1", total=Decimal("120.5000"))
    session.add(extraction)
    await session.commit()
    session.add(
        ValidationIssue(
            document_id=left.id,
            extraction_id=extraction.id,
            code="total_mismatch",
            field="total",
            severity="error",
            message="Total differs",
            related_document_id=right.id,
        )
    )
    session.add(
        CrossCheck(
            left_document_id=left.id,
            right_document_id=right.id,
            left_extraction_id=extraction.id,
            status="unmatched",
            diffs=[],
        )
    )
    await session.commit()

    saved = await session.scalar(select(Extraction))
    assert saved is not None
    assert saved.is_current is True  # a new extraction is current until a newer version replaces it
    assert saved.data["total"] == "120.50"
    assert saved.total == Decimal("120.5000")
    assert saved.created_at is not None
    issue = await session.scalar(select(ValidationIssue))
    assert issue is not None and issue.related_document_id == right.id
    assert await session.scalar(select(func.count()).select_from(CrossCheck)) == 1


async def test_extraction_version_is_unique_per_invoice(session: AsyncSession) -> None:
    document = make_document()
    session.add(document)
    await session.commit()

    session.add_all([make_extraction(document), make_extraction(document)])
    with pytest.raises(IntegrityError):
        await session.commit()


async def test_deleting_a_document_removes_its_extractions_findings_and_cross_checks(
    session: AsyncSession,
) -> None:
    left, right = make_document(), make_document()
    session.add_all([left, right])
    await session.commit()
    extraction = make_extraction(left)
    session.add(extraction)
    await session.commit()
    session.add(
        ValidationIssue(
            document_id=left.id,
            extraction_id=extraction.id,
            code="x",
            severity="error",
            message="m",
        )
    )
    session.add(
        CrossCheck(
            left_document_id=left.id,
            right_document_id=right.id,
            left_extraction_id=extraction.id,
            status="mismatch",
            diffs=[],
        )
    )
    await session.commit()

    await session.execute(delete(Document))
    await session.commit()

    for model in (Extraction, ValidationIssue, CrossCheck):
        assert await session.scalar(select(func.count()).select_from(model)) == 0


async def test_cross_check_survives_deleting_its_extraction(session: AsyncSession) -> None:
    left, right = make_document(), make_document()
    session.add_all([left, right])
    await session.commit()
    extraction = make_extraction(left)
    session.add(extraction)
    await session.commit()
    session.add(
        CrossCheck(
            left_document_id=left.id,
            right_document_id=right.id,
            left_extraction_id=extraction.id,
            status="mismatch",
            diffs=[],
        )
    )
    await session.commit()

    await session.execute(delete(Extraction))
    await session.commit()

    check = await session.scalar(select(CrossCheck).execution_options(populate_existing=True))
    assert check is not None and check.left_extraction_id is None
