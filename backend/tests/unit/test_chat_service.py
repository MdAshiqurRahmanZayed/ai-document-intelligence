import uuid
from typing import Any

import pytest

from app.services.chat import (
    CONTEXT_CHARS,
    NOTHING_FOUND,
    FollowUpSplitter,
    Prepared,
    citations,
    provider_limited,
    select_context,
    stream_answer,
)
from app.services.search import RetrievedChunk
from tests.fake_chat import FakeChatModel

DOC_A, DOC_B = uuid.uuid4(), uuid.uuid4()


def chunk(
    text: str = "text",
    *,
    document: uuid.UUID = DOC_A,
    word: bool = False,
    similarity: float | None = None,
    page: int = 1,
) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=hash((text, page)) % 10_000,
        document_id=document,
        filename="a.pdf" if document == DOC_A else "b.pdf",
        page_no=page,
        text=text,
        word_match=word,
        similarity=similarity,
    )


# --- which chunks the model reads ----------------------------------------------------------


def test_weak_chunks_are_left_out() -> None:
    good = chunk("good", document=DOC_A, similarity=0.9)
    weak = [chunk(f"weak {i}", document=uuid.uuid4(), similarity=0.3) for i in range(5)]

    assert select_context([good, *weak]) == [good]


def test_a_chunk_that_matched_the_words_stays_even_with_low_similarity() -> None:
    matched = chunk("EV-1011", word=True, similarity=0.1)

    assert select_context([matched]) == [matched]


def test_a_chunk_without_a_similarity_or_a_word_match_is_not_relevant() -> None:
    assert select_context([chunk("nothing")]) == []


def test_the_character_limit_keeps_four_chunks_of_a_thousand() -> None:
    chunks = [chunk("x" * 1000, document=uuid.uuid4(), word=True) for _ in range(6)]

    assert select_context(chunks) == chunks[:4]
    assert sum(len(c.text) for c in chunks[:4]) == CONTEXT_CHARS


def test_the_best_chunk_is_kept_whole_even_when_it_is_over_the_limit() -> None:
    huge = chunk("x" * (CONTEXT_CHARS + 500), word=True)
    other = chunk("small", document=DOC_B, word=True)

    assert select_context([huge, other]) == [huge]


def test_a_later_chunk_that_would_pass_the_limit_is_skipped_but_a_smaller_one_fits() -> None:
    first = chunk("a" * 3000, document=DOC_A, word=True)
    too_big = chunk("b" * 2000, document=DOC_B, word=True)
    fits = chunk("c" * 500, document=uuid.uuid4(), word=True)

    assert select_context([first, too_big, fits]) == [first, fits]


def test_at_most_two_chunks_come_from_one_document() -> None:
    from_a = [chunk(f"a{i}", document=DOC_A, word=True, page=i) for i in range(3)]
    from_b = chunk("b", document=DOC_B, word=True)

    assert select_context([*from_a, from_b]) == [from_a[0], from_a[1], from_b]


def test_at_most_six_chunks() -> None:
    chunks = [chunk(f"c{i}", document=uuid.uuid4(), word=True) for i in range(9)]

    assert select_context(chunks) == chunks[:6]


# --- the answer and its follow-up questions ------------------------------------------------


def split(*pieces: str) -> tuple[str, str, list[str]]:
    splitter = FollowUpSplitter()
    sent = "".join(splitter.feed(p) for p in pieces)
    rest, questions = splitter.finish()
    return sent, rest, questions


def test_the_delimiter_in_one_piece() -> None:
    sent, rest, questions = split("It is 120 [1].\n---FOLLOW-UPS---\nWhat is the tax?\nWho paid?")

    assert (sent, rest) == ("It is 120 [1].", "")
    assert questions == ["What is the tax?", "Who paid?"]


def test_the_delimiter_split_over_several_pieces() -> None:
    sent, _, questions = split("It is 120.\n", "---FOLL", "OW-UP", "S---\nWhat ", "is the tax?\n")

    assert sent == "It is 120.\n".rstrip() or sent.rstrip() == "It is 120."
    assert "---" not in sent and "FOLLOW" not in sent
    assert questions == ["What is the tax?"]


def test_without_the_delimiter_there_are_no_suggestions() -> None:
    sent, rest, questions = split("Just ", "an answer.")

    assert sent + rest == "Just an answer." and questions == []


def test_text_that_only_looks_like_the_start_of_the_delimiter_is_released() -> None:
    sent, rest, _ = split("a ---FOLLOW but ", "not it")

    assert sent + rest == "a ---FOLLOW but not it"


def test_more_than_three_questions_are_cut_and_bullets_and_blank_lines_are_dropped() -> None:
    _, _, questions = split("A.\n---FOLLOW-UPS---\n- one\n\n2. two\n* three\nfour\n")

    assert questions == ["one", "two", "three"]


def test_the_follow_up_text_never_reaches_the_answer() -> None:
    sent, _, _ = split("Answer.\n---FOLLOW-UPS---\nSecret question?")

    assert "Secret" not in sent


# --- citations and failures ----------------------------------------------------------------


def test_citations_keep_the_order_of_first_use_and_drop_unknown_numbers() -> None:
    cited, unknown = citations("A [2] and [1][2], also [9].", {1, 2, 3})

    assert cited == [2, 1] and unknown == 1


@pytest.mark.parametrize(
    "error",
    [
        RuntimeError("429 RESOURCE_EXHAUSTED: quota exceeded"),
        RuntimeError("You exceeded your current quota"),
        RuntimeError("Rate limit reached"),
    ],
)
def test_provider_limits_are_recognised(error: Exception) -> None:
    assert provider_limited(error)


def test_other_failures_are_not_provider_limits() -> None:
    assert not provider_limited(RuntimeError("the answer could not be parsed"))


# --- the events ----------------------------------------------------------------------------


async def events(model: FakeChatModel, prepared: Prepared) -> list[tuple[str, dict[str, Any]]]:
    return [event async for event in stream_answer(model, prepared)]


def prepared_with(*chunks: RetrievedChunk, rewritten: bool = False) -> Prepared:
    return Prepared("the question", rewritten, list(chunks))


async def test_events_come_as_sources_tokens_then_done() -> None:
    model = FakeChatModel(["It is ", "120 [1].", "\n---FOLLOW-UPS---\nAnd the tax?"])

    result = await events(model, prepared_with(chunk("Total 120", word=True)))

    assert [name for name, _ in result] == ["sources", "token", "token", "done"]
    sources = result[0][1]["sources"]
    assert sources == [
        {
            "n": 1,
            "document_id": str(DOC_A),
            "filename": "a.pdf",
            "page_no": 1,
            "quote": "Total 120",
        }
    ]
    assert "".join(body["text"] for name, body in result if name == "token") == "It is 120 [1]."
    assert result[-1][1] == {"citations": [1], "suggestions": ["And the tax?"]}


async def test_the_quote_is_plain_text_cut_to_300_characters() -> None:
    long_text = "word  \n" * 200

    result = await events(FakeChatModel(["ok"]), prepared_with(chunk(long_text, word=True)))

    quote = result[0][1]["sources"][0]["quote"]
    assert len(quote) == 300 and "\n" not in quote and "  " not in quote


async def test_sources_are_sent_before_the_model_is_asked() -> None:
    model = FakeChatModel(["x"])
    stream = stream_answer(model, prepared_with(chunk("t", word=True)))

    name, _ = await anext(stream)

    assert name == "sources" and model.stream_calls == []
    await stream.aclose()


async def test_the_model_is_asked_the_standalone_question_with_numbered_chunks() -> None:
    model = FakeChatModel(["x"])

    await events(
        model, prepared_with(chunk("one", word=True), chunk("two", document=DOC_B, word=True))
    )

    assert model.stream_calls == [("the question", [(1, "one"), (2, "two")])]


async def test_nothing_found_makes_no_model_call() -> None:
    model = FakeChatModel(["should not be used"])

    result = await events(model, prepared_with())

    assert result == [
        ("sources", {"sources": []}),
        ("token", {"text": NOTHING_FOUND}),
        ("done", {"citations": [], "suggestions": []}),
    ]
    assert model.stream_calls == []


async def test_an_unknown_marker_is_not_listed_in_the_citations() -> None:
    result = await events(FakeChatModel(["See [1] and [9]."]), prepared_with(chunk("t", word=True)))

    assert result[-1][1]["citations"] == [1]


async def test_the_rewritten_question_is_shown_only_when_there_was_a_rewrite() -> None:
    plain = await events(FakeChatModel(["x"]), prepared_with(chunk("t", word=True)))
    rewritten = await events(
        FakeChatModel(["x"]), prepared_with(chunk("t", word=True), rewritten=True)
    )

    assert "rewritten_question" not in plain[0][1]
    assert rewritten[0][1]["rewritten_question"] == "the question"


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (RuntimeError("429 quota exceeded"), "provider_limited"),
        (RuntimeError("could not parse"), "model_failed"),
    ],
)
async def test_a_failure_ends_the_stream_with_an_error(error: Exception, reason: str) -> None:
    result = await events(FakeChatModel(error=error), prepared_with(chunk("t", word=True)))

    assert [name for name, _ in result] == ["sources", "error"]
    assert result[-1][1] == {"reason": reason}


async def test_a_failure_after_some_text_keeps_the_text_and_sends_an_error() -> None:
    model = FakeChatModel(["Part of the ", "answer"], error=RuntimeError("connection reset"))

    result = await events(model, prepared_with(chunk("t", word=True)))

    assert [name for name, _ in result] == ["sources", "token", "token", "error"]
    assert result[-1][1] == {"reason": "model_failed"}
