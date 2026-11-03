from decimal import Decimal

import pytest
from sqlalchemy import Text, cast, delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Chunk,
    Correction,
    CrossCheck,
    Document,
    DocumentStatus,
    Extraction,
    Page,
    ProcessingEvent,
    ValidationIssue,
)
from app.db.types import EMBEDDING_DIM
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


def vector(*hot: int) -> list[float]:
    """An embedding that is 1.0 at the given positions and 0.0 elsewhere."""
    return [1.0 if i in hot else 0.0 for i in range(EMBEDDING_DIM)]


async def test_a_correction_is_saved_and_read_back(session: AsyncSession) -> None:
    document = make_document()
    session.add(document)
    await session.commit()
    extraction = make_extraction(document)
    session.add(extraction)
    await session.commit()
    session.add(
        Correction(
            document_id=document.id,
            extraction_id=extraction.id,
            field="total",
            old_value="130.00",
            new_value="120.00",
            edited_by="reviewer",
        )
    )
    await session.commit()

    saved = await session.scalar(select(Correction))

    assert saved is not None
    assert (saved.field, saved.old_value, saved.new_value) == ("total", "130.00", "120.00")
    assert saved.edited_by == "reviewer" and saved.created_at is not None


async def test_a_chunk_gets_its_search_vector_from_the_database(session: AsyncSession) -> None:
    document = make_document()
    session.add(document)
    await session.commit()
    session.add(Chunk(document_id=document.id, page_no=1, chunk_no=0, text="Invoice for Acme"))
    await session.commit()

    # Read as text: this checks what the database generated, not a driver's tsvector decoding.
    tsv = await session.scalar(select(cast(Chunk.tsv, Text)))
    chunk = await session.scalar(select(Chunk))

    assert tsv is not None and "'acme'" in tsv and "'invoice'" in tsv
    assert chunk is not None and chunk.embedding is None  # not embedded yet


async def test_an_embedding_survives_a_round_trip(session: AsyncSession) -> None:
    document = make_document()
    session.add(document)
    await session.commit()
    session.add(
        Chunk(document_id=document.id, page_no=1, chunk_no=0, text="x", embedding=vector(3, 5))
    )
    await session.commit()

    chunk = await session.scalar(select(Chunk).execution_options(populate_existing=True))

    assert chunk is not None and chunk.embedding == vector(3, 5)


async def test_chunks_are_ordered_by_cosine_distance(session: AsyncSession) -> None:
    document = make_document()
    session.add(document)
    await session.commit()
    session.add_all(
        [
            Chunk(document_id=document.id, page_no=1, chunk_no=0, text="far", embedding=vector(9)),
            Chunk(
                document_id=document.id, page_no=1, chunk_no=1, text="near", embedding=vector(1, 2)
            ),
            Chunk(document_id=document.id, page_no=1, chunk_no=2, text="none"),  # no embedding
        ]
    )
    await session.commit()

    distance = Chunk.embedding.op("<=>")(vector(1))
    texts = await session.scalars(
        select(Chunk.text).where(Chunk.embedding.is_not(None)).order_by(distance)
    )

    assert list(texts) == ["near", "far"]


async def test_chunk_position_is_unique_per_page(session: AsyncSession) -> None:
    document = make_document()
    session.add(document)
    await session.commit()

    session.add_all(
        [
            Chunk(document_id=document.id, page_no=1, chunk_no=0, text="a"),
            Chunk(document_id=document.id, page_no=1, chunk_no=0, text="b"),
        ]
    )
    with pytest.raises(IntegrityError):
        await session.commit()


async def test_deleting_a_document_removes_its_corrections_and_chunks(
    session: AsyncSession,
) -> None:
    document = make_document()
    session.add(document)
    await session.commit()
    extraction = make_extraction(document)
    session.add(extraction)
    await session.commit()
    session.add(
        Correction(
            document_id=document.id,
            extraction_id=extraction.id,
            field="total",
            old_value=None,
            new_value="1",
            edited_by="api",
        )
    )
    session.add(Chunk(document_id=document.id, page_no=1, chunk_no=0, text="a"))
    await session.commit()

    await session.execute(delete(Document))
    await session.commit()

    for model in (Correction, Chunk):
        assert await session.scalar(select(func.count()).select_from(model)) == 0


def test_the_vector_column_has_the_size_the_embedder_produces() -> None:
    column_type = Chunk.__table__.c.embedding.type

    assert column_type.dim == EMBEDDING_DIM == 768  # type: ignore[attr-defined]
