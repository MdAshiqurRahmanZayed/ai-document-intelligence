"""Search over document chunks: by words, by meaning, or both."""

import asyncio
import html
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import ColumnElement, Float, Select, func, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chunk, Document
from app.llm.embeddings import Embedder
from app.services.listing import (
    DocumentFilters,
    InvoiceSummary,
    document_conditions,
    invoice_summaries,
)

Mode = Literal["keyword", "semantic", "hybrid"]

TOP_CHUNKS = 50  # candidates taken from each ranking before they are reduced to documents
RRF_K = 60  # the usual constant of reciprocal rank fusion: it keeps one top rank from dominating
PLAIN_SNIPPET_CHARS = 200

# ts_headline marks matches with these. They are private-use characters, so they cannot be
# confused with anything in a document; they are swapped for <mark> after the text is escaped.
MARK_START, MARK_STOP = "", ""
HEADLINE_OPTIONS = f"StartSel={MARK_START}, StopSel={MARK_STOP}, MaxWords=30, MinWords=10"
# The text search configuration must reach PostgreSQL as a regconfig. A bound string parameter is
# sent as varchar, which PostgreSQL does not convert to regconfig, so it is written into the SQL.
SIMPLE: ColumnElement[Any] = literal_column("'simple'::regconfig")


class SemanticUnavailable(Exception):
    """Semantic search needs an embedding model, which needs a Google API key."""


@dataclass(frozen=True)
class ChunkHit:
    chunk_id: int
    document_id: uuid.UUID
    page_no: int
    score: float
    snippet: str  # safe to show as HTML


@dataclass(frozen=True)
class SearchResult:
    document: Document
    page_no: int
    snippet: str
    score: float
    invoices: list[InvoiceSummary]


@dataclass(frozen=True)
class SearchOutcome:
    mode_used: Mode
    results: list[SearchResult]


@dataclass(frozen=True)
class RetrievedChunk:
    """A chunk with its whole text, as the answering model needs it."""

    chunk_id: int
    document_id: uuid.UUID
    filename: str
    page_no: int
    text: str
    word_match: bool  # the keyword search found it
    similarity: float | None  # cosine similarity to the query; None if semantic search did not


def keyword_snippet(headline: str) -> str:
    """Escape everything the document said, then turn the match markers into <mark> tags."""
    return html.escape(headline).replace(MARK_START, "<mark>").replace(MARK_STOP, "</mark>")


def plain_snippet(text: str) -> str:
    return html.escape(text[:PLAIN_SNIPPET_CHARS])


def reciprocal_rank_fusion(rankings: Sequence[Sequence[int]], k: int = RRF_K) -> dict[int, float]:
    """Score of an item = the sum of 1 / (k + rank) over the rankings that contain it (rank 1
    is best). An item near the top of two rankings beats one at the top of only one."""
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
    return scores


def best_chunk_per_document(hits: Sequence[ChunkHit]) -> list[ChunkHit]:
    """Keep the first (best) hit of every document; `hits` must be ordered best first."""
    seen: set[uuid.UUID] = set()
    best = []
    for hit in hits:
        if hit.document_id not in seen:
            seen.add(hit.document_id)
            best.append(hit)
    return best


def _allowed_documents(filters: DocumentFilters) -> Select[uuid.UUID]:
    return select(Document.id).where(*document_conditions(filters))


async def keyword_hits(
    session: AsyncSession, query: str, filters: DocumentFilters, limit: int = TOP_CHUNKS
) -> list[ChunkHit]:
    # websearch syntax: words are ANDed, "quoted phrases" and -excluded words work. "simple"
    # means no stemming, matching the generated tsv column.
    tsquery = func.websearch_to_tsquery(SIMPLE, query)
    rank = func.ts_rank_cd(Chunk.tsv, tsquery)
    headline = func.ts_headline(SIMPLE, Chunk.text, tsquery, HEADLINE_OPTIONS)
    rows = await session.execute(
        select(Chunk.id, Chunk.document_id, Chunk.page_no, rank, headline)
        .where(Chunk.tsv.op("@@")(tsquery), Chunk.document_id.in_(_allowed_documents(filters)))
        .order_by(rank.desc(), Chunk.id)
        .limit(limit)
    )
    return [
        ChunkHit(chunk_id, document_id, page_no, float(score), keyword_snippet(text))
        for chunk_id, document_id, page_no, score, text in rows
    ]


async def semantic_hits(
    session: AsyncSession,
    vector: list[float],
    filters: DocumentFilters,
    limit: int = TOP_CHUNKS,
) -> list[ChunkHit]:
    # Cosine distance: 0 is the same direction, 2 the opposite. Chunks without an embedding
    # (not embedded yet, or no key) are not candidates.
    distance = Chunk.embedding.op("<=>", return_type=Float)(vector)
    rows = await session.execute(
        select(Chunk.id, Chunk.document_id, Chunk.page_no, distance, Chunk.text)
        .where(Chunk.embedding.is_not(None), Chunk.document_id.in_(_allowed_documents(filters)))
        .order_by(distance, Chunk.id)
        .limit(limit)
    )
    return [
        ChunkHit(chunk_id, document_id, page_no, 1.0 - float(dist), plain_snippet(text))
        for chunk_id, document_id, page_no, dist, text in rows
    ]


def fuse(keyword: Sequence[ChunkHit], semantic: Sequence[ChunkHit]) -> list[ChunkHit]:
    """Combine two rankings of chunks into one, best first (reciprocal rank fusion)."""
    scores = reciprocal_rank_fusion([[h.chunk_id for h in keyword], [h.chunk_id for h in semantic]])
    # A chunk found by words has a snippet with the matches marked: prefer it.
    by_chunk = {h.chunk_id: h for h in [*semantic, *keyword]}
    ordered = sorted(scores, key=lambda chunk_id: (-scores[chunk_id], chunk_id))
    return [
        ChunkHit(c, by_chunk[c].document_id, by_chunk[c].page_no, scores[c], by_chunk[c].snippet)
        for c in ordered
    ]


async def search(
    session: AsyncSession,
    query: str,
    mode: Mode,
    filters: DocumentFilters,
    limit: int,
    embedder: Embedder | None,
) -> SearchOutcome:
    if mode == "semantic" and embedder is None:
        raise SemanticUnavailable
    if embedder is None:  # hybrid without a model is just keyword search
        mode = "keyword"

    keyword = await keyword_hits(session, query, filters) if mode != "semantic" else []
    semantic: list[ChunkHit] = []
    if mode != "keyword" and embedder is not None:
        # The model call is blocking network I/O, so it runs in a thread, off the event loop.
        vector = await asyncio.to_thread(embedder.embed_query, query)
        semantic = await semantic_hits(session, vector, filters)

    ranked = fuse(keyword, semantic) if mode == "hybrid" else keyword or semantic
    best = best_chunk_per_document(ranked)[:limit]

    found = await session.scalars(
        select(Document).where(Document.id.in_([h.document_id for h in best]))
    )
    documents = {d.id: d for d in found}
    summaries = await invoice_summaries(session, list(documents))
    return SearchOutcome(
        mode_used=mode,
        results=[
            SearchResult(
                documents[h.document_id],
                h.page_no,
                h.snippet,
                h.score,
                summaries.get(h.document_id, []),
            )
            for h in best
        ],
    )


# Chunks loaded with their text after ranking: enough for the caller to choose from, without
# reading all the candidates of both rankings.
RETRIEVED_CHUNKS = 20


async def retrieve_chunks(
    session: AsyncSession,
    query: str,
    filters: DocumentFilters,
    embedder: Embedder | None,
) -> list[RetrievedChunk]:
    """The best chunks for a query, best first, with their text. The ranking is the one of
    hybrid search; without an embedder it is keyword search."""
    keyword = await keyword_hits(session, query, filters)
    semantic: list[ChunkHit] = []
    if embedder is not None:
        vector = await asyncio.to_thread(embedder.embed_query, query)
        semantic = await semantic_hits(session, vector, filters)

    ranked = fuse(keyword, semantic)[:RETRIEVED_CHUNKS]
    if not ranked:
        return []
    matched = {h.chunk_id for h in keyword}
    similarity = {h.chunk_id: h.score for h in semantic}

    rows = await session.execute(
        select(Chunk.id, Chunk.document_id, Chunk.page_no, Chunk.text, Document.filename)
        .join(Document, Document.id == Chunk.document_id)
        .where(Chunk.id.in_([h.chunk_id for h in ranked]))
    )
    by_id = {row.id: row for row in rows}
    return [
        RetrievedChunk(
            chunk_id=h.chunk_id,
            document_id=h.document_id,
            filename=by_id[h.chunk_id].filename,
            page_no=h.page_no,
            text=by_id[h.chunk_id].text,
            word_match=h.chunk_id in matched,
            similarity=similarity.get(h.chunk_id),
        )
        for h in ranked
    ]
