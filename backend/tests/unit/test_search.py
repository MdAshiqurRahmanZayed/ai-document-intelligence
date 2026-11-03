import uuid

import pytest

from app.services.search import (
    MARK_START,
    MARK_STOP,
    ChunkHit,
    best_chunk_per_document,
    fuse,
    keyword_snippet,
    plain_snippet,
    reciprocal_rank_fusion,
)


def test_a_script_in_a_document_is_escaped_and_only_the_marks_are_markup() -> None:
    headline = f"<script>alert(1)</script> an {MARK_START}invoice{MARK_STOP} & more"

    snippet = keyword_snippet(headline)

    assert snippet == "&lt;script&gt;alert(1)&lt;/script&gt; an <mark>invoice</mark> &amp; more"
    assert "<script>" not in snippet


def test_the_plain_snippet_is_short_and_escaped() -> None:
    snippet = plain_snippet("<b>" + "x" * 500)

    assert snippet.startswith("&lt;b&gt;") and len(snippet) < 260 and "<b>" not in snippet


def test_fusion_adds_one_over_k_plus_rank_for_every_ranking_an_item_is_in() -> None:
    scores = reciprocal_rank_fusion([[1, 2, 3], [3, 4]], k=60)

    assert scores[1] == pytest.approx(1 / 61)
    assert scores[2] == pytest.approx(1 / 62)
    assert scores[3] == pytest.approx(1 / 63 + 1 / 61)  # third in one list, first in the other
    assert scores[4] == pytest.approx(1 / 62)


def test_an_item_near_the_top_of_two_rankings_beats_the_top_of_one() -> None:
    scores = reciprocal_rank_fusion([[10, 7], [20, 7]])

    assert scores[7] > scores[10] and scores[7] > scores[20]


def hit(chunk_id: int, document: uuid.UUID, snippet: str = "s", page: int = 1) -> ChunkHit:
    return ChunkHit(chunk_id, document, page, 0.0, snippet)


def test_fuse_orders_by_score_and_prefers_the_snippet_with_marks() -> None:
    doc = uuid.uuid4()
    keyword = [hit(1, doc, "<mark>words</mark>"), hit(2, doc, "<mark>only words</mark>")]
    semantic = [hit(1, doc, "plain text"), hit(3, doc, "only meaning")]

    fused = fuse(keyword, semantic)

    assert [h.chunk_id for h in fused] == [1, 2, 3]  # in both, then rank 2 keyword, rank 2 semantic
    assert fused[0].snippet == "<mark>words</mark>"
    assert fused[0].score > fused[1].score >= fused[2].score


def test_the_best_chunk_of_each_document_is_kept_in_order() -> None:
    first, second = uuid.uuid4(), uuid.uuid4()
    hits = [hit(1, first), hit(2, second), hit(3, first), hit(4, second)]

    assert [h.chunk_id for h in best_chunk_per_document(hits)] == [1, 2]
