import re

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DocumentStatus
from app.services.listing import DocumentFilters
from app.services.search import (
    Mode,
    SearchOutcome,
    SemanticUnavailable,
    retrieve_chunks,
    search,
)
from tests.fake_embedder import FakeEmbedder
from tests.search_samples import indexed

NO_FILTERS = DocumentFilters()


async def run(
    session: AsyncSession,
    query: str,
    mode: Mode = "keyword",
    filters: DocumentFilters = NO_FILTERS,
    embedder: FakeEmbedder | None = None,
    limit: int = 10,
) -> SearchOutcome:
    return await search(session, query, mode, filters, limit, embedder)


def names(outcome: SearchOutcome) -> list[str]:
    return [r.document.filename for r in outcome.results]


# --- keyword ------------------------------------------------------------------------------


async def test_every_word_must_match_in_any_order(session: AsyncSession) -> None:
    await indexed(session, "Cover page", "Acme Industries invoice", name="acme.pdf")
    await indexed(session, "Only Acme here", name="partial.pdf")

    outcome = await run(session, "industries acme")

    assert names(outcome) == ["acme.pdf"]
    (result,) = outcome.results
    assert result.page_no == 2
    marked = " ".join(re.findall(r"<mark>(.*?)</mark>", result.snippet))
    assert "Acme" in marked and "Industries" in marked


async def test_words_that_are_nowhere_give_an_empty_list(session: AsyncSession) -> None:
    await indexed(session, "Acme Industries invoice")

    outcome = await run(session, "zebra")

    assert outcome.results == [] and outcome.mode_used == "keyword"


async def test_a_document_appears_once_with_its_best_chunk(session: AsyncSession) -> None:
    await indexed(session, "invoice one", "invoice two", "invoice three", "invoice invoice invoice")

    outcome = await run(session, "invoice")

    assert len(outcome.results) == 1
    assert outcome.results[0].page_no == 4  # the page where the word is densest


async def test_filters_narrow_the_results(session: AsyncSession) -> None:
    await indexed(session, "an invoice", name="done.pdf", status=DocumentStatus.COMPLETED)
    await indexed(session, "an invoice", name="review.pdf", status=DocumentStatus.NEEDS_REVIEW)

    outcome = await run(session, "invoice", filters=DocumentFilters(status="NEEDS_REVIEW"))

    assert names(outcome) == ["review.pdf"]


def only_mark_tags(snippet: str) -> bool:
    """True when the snippet has no markup except <mark> and </mark>."""
    return "<" not in snippet.replace("<mark>", "").replace("</mark>", "")


async def test_markup_in_a_document_cannot_reach_the_client(session: AsyncSession) -> None:
    await indexed(session, "<script>alert(1)</script> invoice")

    (result,) = (await run(session, "invoice")).results

    # PostgreSQL's headline leaves HTML tags out; anything it kept is escaped by the server.
    assert "<script" not in result.snippet and "</script" not in result.snippet
    assert only_mark_tags(result.snippet)
    assert "<mark>invoice</mark>" in result.snippet


async def test_results_carry_the_invoice_summary(session: AsyncSession) -> None:
    from tests.listing_samples import add_invoice

    document = await indexed(session, "an invoice")
    await add_invoice(session, document, number="INV-9", total="12.00")

    (result,) = (await run(session, "invoice")).results

    assert [(i.invoice_number, str(i.total)) for i in result.invoices] == [("INV-9", "12.0000")]


# --- semantic and hybrid --------------------------------------------------------------------


async def test_semantic_search_finds_meaning_not_words(session: AsyncSession) -> None:
    await indexed(session, "bananas are yellow fruit", name="fruit.pdf")
    await indexed(session, "payment is due within thirty days", name="terms.pdf")

    outcome = await run(session, "when must I pay", "semantic", embedder=FakeEmbedder())

    assert names(outcome)[0] == "terms.pdf"  # shares no word with the question, only its meaning
    assert outcome.mode_used == "semantic"
    assert outcome.results[0].score > outcome.results[-1].score


async def test_chunks_without_an_embedding_are_not_found_semantically(
    session: AsyncSession,
) -> None:
    await indexed(session, "payment is due", name="not-embedded.pdf", embedded=False)

    outcome = await run(session, "pay", "semantic", embedder=FakeEmbedder())

    assert outcome.results == []


async def test_semantic_search_without_a_model_is_refused(session: AsyncSession) -> None:
    with pytest.raises(SemanticUnavailable):
        await run(session, "pay", "semantic", embedder=None)


async def test_a_chunk_found_by_words_and_meaning_outranks_one_found_by_meaning_only(
    session: AsyncSession,
) -> None:
    await indexed(session, "payment due now", name="both.pdf")  # words match and meaning matches
    await indexed(session, "settle the owed amount", name="meaning-only.pdf")

    outcome = await run(session, "payment due", "hybrid", embedder=FakeEmbedder())

    assert names(outcome) == ["both.pdf", "meaning-only.pdf"]
    assert outcome.mode_used == "hybrid"
    assert outcome.results[0].score > outcome.results[1].score


async def test_hybrid_without_a_model_is_keyword_search(session: AsyncSession) -> None:
    await indexed(session, "payment due now", name="words.pdf")
    await indexed(session, "settle the owed amount", name="meaning-only.pdf")

    hybrid = await run(session, "payment due", "hybrid", embedder=None)
    keyword = await run(session, "payment due", "keyword")

    assert names(hybrid) == names(keyword) == ["words.pdf"]
    assert hybrid.mode_used == "keyword"


async def test_the_limit_and_filters_apply_to_semantic_search_too(session: AsyncSession) -> None:
    for n in range(3):
        status = DocumentStatus.NEEDS_REVIEW if n == 0 else DocumentStatus.COMPLETED
        await indexed(session, "payment is due", name=f"d{n}.pdf", status=status)

    limited = await run(session, "pay", "semantic", embedder=FakeEmbedder(), limit=2)
    filtered = await run(
        session,
        "pay",
        "semantic",
        filters=DocumentFilters(status="NEEDS_REVIEW"),
        embedder=FakeEmbedder(),
    )

    assert len(limited.results) == 2
    assert names(filtered) == ["d0.pdf"]


# --- chunks for chat ----------------------------------------------------------------------


async def test_retrieved_chunks_carry_their_text_and_how_they_were_found(
    session: AsyncSession,
) -> None:
    await indexed(session, "Cover page", "Acme Industries invoice, hosting", name="acme.pdf")

    chunks = await retrieve_chunks(session, "acme hosting", NO_FILTERS, FakeEmbedder())

    best = chunks[0]
    assert best.filename == "acme.pdf" and best.page_no == 2
    assert best.text == "Acme Industries invoice, hosting"
    assert best.word_match is True
    assert best.similarity is not None and best.similarity > 0


async def test_a_chunk_found_only_by_meaning_has_no_word_match(session: AsyncSession) -> None:
    await indexed(session, "delivery is scheduled for Monday", name="ship.pdf")

    # "shipping" and "delivery" are the same thing to the fake embedder, but share no word
    (chunk,) = await retrieve_chunks(session, "shipping", NO_FILTERS, FakeEmbedder())

    assert chunk.word_match is False
    assert chunk.similarity is not None and chunk.similarity > 0.4


async def test_retrieved_chunks_follow_the_filters(session: AsyncSession) -> None:
    await indexed(session, "an invoice", name="done.pdf", status=DocumentStatus.COMPLETED)
    await indexed(session, "an invoice", name="review.pdf", status=DocumentStatus.NEEDS_REVIEW)

    chunks = await retrieve_chunks(
        session, "invoice", DocumentFilters(status="NEEDS_REVIEW"), FakeEmbedder()
    )

    assert {c.filename for c in chunks} == {"review.pdf"}


async def test_without_an_embedder_chunks_come_from_keyword_search(session: AsyncSession) -> None:
    await indexed(session, "Acme Industries invoice", name="acme.pdf")

    chunks = await retrieve_chunks(session, "acme", NO_FILTERS, None)

    assert [c.filename for c in chunks] == ["acme.pdf"]
    assert chunks[0].word_match is True and chunks[0].similarity is None


async def test_no_chunk_when_nothing_matches_and_nothing_is_embedded(
    session: AsyncSession,
) -> None:
    await indexed(session, "Acme Industries invoice", embedded=False)

    assert await retrieve_chunks(session, "zebra", NO_FILTERS, FakeEmbedder()) == []
