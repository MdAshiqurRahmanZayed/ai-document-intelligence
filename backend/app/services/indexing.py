"""Splits a document's text into searchable chunks and gives them embeddings."""

import asyncio
import uuid

from langchain_text_splitters import RecursiveCharacterTextSplitter
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chunk, Page
from app.llm.embeddings import Embedder

CHUNK_SIZE = 1000  # characters: small enough to match one topic, large enough to keep context
CHUNK_OVERLAP = 150  # so a sentence cut at a boundary is whole in one of the two chunks
EMBED_BATCH = 50  # chunks sent to the model per call


async def index_chunks(session: AsyncSession, document_id: uuid.UUID) -> int:
    """Replace the document's chunks with chunks of its current page text.

    Runs inside the caller's transaction (it does not commit), so a document is never marked
    done without its chunks. Pages without text produce none. Returns the number of chunks.
    """
    rows = await session.execute(
        select(Page.page_no, Page.text)
        .where(Page.document_id == document_id, Page.text.is_not(None))
        .order_by(Page.page_no)
    )
    splitter = RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP)
    chunks = [
        Chunk(document_id=document_id, page_no=page_no, chunk_no=position, text=piece)
        for page_no, text in rows
        for position, piece in enumerate(splitter.split_text(text or ""))
        if piece.strip()
    ]
    await session.execute(delete(Chunk).where(Chunk.document_id == document_id))
    session.add_all(chunks)
    return len(chunks)


async def embed_missing_chunks(
    session: AsyncSession,
    document_id: uuid.UUID,
    embedder: Embedder,
    batch_size: int = EMBED_BATCH,
) -> int:
    """Embed the chunks that have no embedding yet, committing after each batch.

    Safe to run again: finished chunks are skipped, so a retry only redoes the rest.
    """
    done = 0
    while True:
        chunks = list(
            await session.scalars(
                select(Chunk)
                .where(Chunk.document_id == document_id, Chunk.embedding.is_(None))
                .order_by(Chunk.id)
                .limit(batch_size)
            )
        )
        if not chunks:
            return done
        # The model call is blocking network I/O, so it runs in a thread, off the event loop.
        vectors = await asyncio.to_thread(embedder.embed_documents, [c.text for c in chunks])
        for chunk, vector in zip(chunks, vectors, strict=True):
            chunk.embedding = vector
        await session.commit()
        done += len(chunks)
