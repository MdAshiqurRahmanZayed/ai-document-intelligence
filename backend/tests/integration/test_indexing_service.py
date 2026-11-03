import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chunk, Document, Page
from app.services.indexing import embed_missing_chunks, index_chunks
from tests.fake_embedder import FakeEmbedder, embed
from tests.helpers import make_document


async def document_with_pages(session: AsyncSession, *texts: str | None) -> Document:
    document = make_document()
    session.add(document)
    await session.commit()
    session.add_all(
        Page(document_id=document.id, page_no=n, text=text, method="native")
        for n, text in enumerate(texts, start=1)
    )
    await session.commit()
    return document


async def chunks_of(session: AsyncSession, document: Document) -> list[Chunk]:
    rows = await session.scalars(
        select(Chunk)
        .where(Chunk.document_id == document.id)
        .order_by(Chunk.page_no, Chunk.chunk_no)
        .execution_options(populate_existing=True)
    )
    return list(rows)


async def test_every_page_with_text_gets_chunks_that_know_their_page(
    session: AsyncSession,
) -> None:
    document = await document_with_pages(session, "Invoice for Acme", "Total due 120.00")

    count = await index_chunks(session, document.id)
    await session.commit()

    chunks = await chunks_of(session, document)
    assert count == 2
    assert [(c.page_no, c.chunk_no, c.text) for c in chunks] == [
        (1, 0, "Invoice for Acme"),
        (2, 0, "Total due 120.00"),
    ]


async def test_a_long_page_is_split_into_overlapping_chunks(session: AsyncSession) -> None:
    text = " ".join(f"word{n:03d}" for n in range(300))  # about 2400 characters
    document = await document_with_pages(session, text)

    await index_chunks(session, document.id)
    await session.commit()

    chunks = await chunks_of(session, document)
    assert len(chunks) >= 3 and all(len(c.text) <= 1000 for c in chunks)
    assert [c.chunk_no for c in chunks] == list(range(len(chunks)))
    for earlier, later in zip(chunks, chunks[1:], strict=False):
        assert later.text.split()[0] in earlier.text  # the end of one reappears at the next start


async def test_indexing_again_replaces_the_chunks(session: AsyncSession) -> None:
    document = await document_with_pages(session, "first version of the text")
    await index_chunks(session, document.id)
    await session.commit()
    page = await session.scalar(select(Page).where(Page.document_id == document.id))
    assert page is not None
    page.text = "second version of the text"
    await session.commit()

    await index_chunks(session, document.id)
    await session.commit()

    assert [c.text for c in await chunks_of(session, document)] == ["second version of the text"]


async def test_pages_without_text_make_no_chunks(session: AsyncSession) -> None:
    document = await document_with_pages(session, "real text", "", "   ", None)

    count = await index_chunks(session, document.id)
    await session.commit()

    assert count == 1
    assert [c.page_no for c in await chunks_of(session, document)] == [1]


async def test_embeddings_are_added_only_where_missing(session: AsyncSession) -> None:
    document = await document_with_pages(session, "payment due soon", "delivery next week")
    await index_chunks(session, document.id)
    await session.commit()
    first, second = await chunks_of(session, document)
    kept = [0.5] * 768
    first.embedding = kept  # already embedded earlier
    await session.commit()
    embedder = FakeEmbedder()

    done = await embed_missing_chunks(session, document.id, embedder)

    assert done == 1 and embedder.embedded == ["delivery next week"]
    first, second = await chunks_of(session, document)
    assert first.embedding == kept  # 0.5 is exact in 32 bits
    # pgvector keeps each number as a 32-bit float, so a computed value comes back slightly
    # rounded (0.7071067811865476 becomes 0.7071067690849304).
    assert second.embedding == pytest.approx(embed("delivery next week"), rel=1e-6)


async def test_embedding_goes_in_batches_and_stops_when_nothing_is_missing(
    session: AsyncSession,
) -> None:
    document = await document_with_pages(session, *[f"page number {n}" for n in range(5)])
    await index_chunks(session, document.id)
    await session.commit()
    embedder = FakeEmbedder()

    done = await embed_missing_chunks(session, document.id, embedder, batch_size=2)
    again = await embed_missing_chunks(session, document.id, embedder, batch_size=2)

    assert (done, again) == (5, 0) and len(embedder.embedded) == 5
