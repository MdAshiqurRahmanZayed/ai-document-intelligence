"""Answers a question from the text of the stored documents. No FastAPI imports.

Two steps so that the database is not held while the model writes: `prepare` finds what to read,
`stream_answer` asks the model and turns what it writes into events.
"""

import asyncio
import re
import uuid
from collections import Counter
from collections.abc import AsyncGenerator, AsyncIterator, Iterator, Sequence
from dataclasses import dataclass
from typing import Any, Final, cast

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.chat import FOLLOW_UPS_DELIMITER, ChatModel, Turn
from app.llm.embeddings import Embedder
from app.services.listing import DocumentFilters
from app.services.search import RetrievedChunk, retrieve_chunks

log = structlog.get_logger()

MAX_CHUNKS = 6
PER_DOCUMENT = 2
CONTEXT_CHARS = 4000  # characters of chunk text given to the model (about 1000 tokens)
# Meaning similarity a chunk needs when it did not match the question's words. Similarities are
# bunched together: on the sample invoices the best chunk of an answerable question scored 0.64 to
# 0.74 and the best chunk of an off-topic one 0.49 to 0.61 ("hello" was highest), so 0.62 sits
# between them. Nine questions on one small set: treat it as a starting point (design.md).
MIN_SIMILARITY = 0.62
QUOTE_CHARS = 300
MAX_SUGGESTIONS = 3
REWRITE_CHARS = 500  # the longest a rewritten question may be

NOTHING_FOUND = (
    "I couldn't find anything in the documents that answers this. "
    "Try other words, or remove a filter."
)

Event = tuple[str, dict[str, Any]]  # name, body


def select_context(
    chunks: Sequence[RetrievedChunk], min_similarity: float = MIN_SIMILARITY
) -> list[RetrievedChunk]:
    """The chunks the model gets: the relevant ones, best first, within the limits.

    The best relevant chunk is always kept whole; a later chunk that would pass the character
    limit is left out.
    """
    chosen: list[RetrievedChunk] = []
    per_document: Counter[uuid.UUID] = Counter()
    used = 0
    for chunk in chunks:
        relevant = chunk.word_match or (
            chunk.similarity is not None and chunk.similarity >= min_similarity
        )
        if not relevant or per_document[chunk.document_id] >= PER_DOCUMENT:
            continue
        if chosen and used + len(chunk.text) > CONTEXT_CHARS:
            continue
        chosen.append(chunk)
        per_document[chunk.document_id] += 1
        used += len(chunk.text)
        if len(chosen) == MAX_CHUNKS:
            break
    return chosen


class FollowUpSplitter:
    """Separates the answer from the follow-up questions in a stream of text.

    Text is passed on as soon as it cannot be the start of the delimiter; what follows the
    delimiter is kept and read as questions at the end.
    """

    def __init__(self) -> None:
        self._held = ""
        self._questions = ""
        self._found = False

    def feed(self, text: str) -> str:
        """The part of the answer that is safe to send now."""
        if self._found:
            self._questions += text
            return ""
        self._held += text
        at = self._held.find(FOLLOW_UPS_DELIMITER)
        if at >= 0:
            self._found = True
            answer, self._questions = (
                self._held[:at].rstrip(),
                self._held[at + len(FOLLOW_UPS_DELIMITER) :],
            )
            self._held = ""
            return answer
        keep = _partial_delimiter(self._held)
        send, self._held = (
            self._held[: len(self._held) - keep],
            self._held[len(self._held) - keep :],
        )
        return send

    def finish(self) -> tuple[str, list[str]]:
        """Text still held back, and the suggested questions."""
        rest, self._held = ("" if self._found else self._held), ""
        questions = []
        for line in self._questions.splitlines():
            line = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", line).strip()
            if line:
                questions.append(line)
        return rest, questions[:MAX_SUGGESTIONS]


def _partial_delimiter(text: str) -> int:
    """Length of the longest end of `text` that is the start of the delimiter."""
    for size in range(min(len(text), len(FOLLOW_UPS_DELIMITER) - 1), 0, -1):
        if FOLLOW_UPS_DELIMITER.startswith(text[-size:]):
            return size
    return 0


@dataclass(frozen=True)
class Prepared:
    question: str  # the one used to retrieve and to answer
    rewritten: bool
    chunks: list[RetrievedChunk]


async def prepare(
    session: AsyncSession,
    model: ChatModel,
    embedder: Embedder | None,
    question: str,
    history: Sequence[Turn],
    filters: DocumentFilters,
) -> Prepared:
    standalone, rewritten = question, False
    if history:  # the history is read here and nowhere else
        try:
            text = (await asyncio.to_thread(model.rewrite, history, question)).strip()
        except Exception:
            log.warning("chat_rewrite_failed", exc_info=True)
        else:
            if text:
                standalone, rewritten = text[:REWRITE_CHARS], True
    found = await retrieve_chunks(session, standalone, filters, embedder)
    return Prepared(standalone, rewritten, select_context(found))


_MARKER = re.compile(r"\[(\d+)\]")


def citations(text: str, numbers: set[int]) -> tuple[list[int], int]:
    """The source numbers an answer cites, in order of first use, and how many markers named
    a source that does not exist."""
    cited: list[int] = []
    unknown = 0
    for match in _MARKER.finditer(text):
        number = int(match.group(1))
        if number not in numbers:
            unknown += 1
        elif number not in cited:
            cited.append(number)
    return cited, unknown


_PROVIDER_LIMIT = ("429", "resource_exhausted", "resourceexhausted", "quota", "rate limit")


def provider_limited(exc: BaseException) -> bool:
    """True when the provider refused for quota or rate, which is not the question's fault."""
    text = f"{type(exc).__name__} {exc}".lower()
    return any(marker in text for marker in _PROVIDER_LIMIT)


_END: Final = object()


async def _pieces(iterator: Iterator[str]) -> AsyncIterator[str]:
    """The pieces of a blocking iterator, each fetched in a thread so the loop stays free."""
    while (item := await asyncio.to_thread(next, iterator, _END)) is not _END:
        yield cast(str, item)


def quote(text: str) -> str:
    return " ".join(text.split())[:QUOTE_CHARS]


async def stream_answer(model: ChatModel, prepared: Prepared) -> AsyncGenerator[Event]:
    sources = [
        {
            "n": number,
            "document_id": str(chunk.document_id),
            "filename": chunk.filename,
            "page_no": chunk.page_no,
            "quote": quote(chunk.text),
        }
        for number, chunk in enumerate(prepared.chunks, start=1)
    ]
    head: dict[str, Any] = {"sources": sources}
    if prepared.rewritten:
        head["rewritten_question"] = prepared.question
    yield "sources", head

    if not prepared.chunks:
        yield "token", {"text": NOTHING_FOUND}
        yield "done", {"citations": [], "suggestions": []}
        return

    splitter = FollowUpSplitter()
    sent: list[str] = []
    numbered = [(n, c.text) for n, c in enumerate(prepared.chunks, start=1)]
    try:
        async for piece in _pieces(model.stream(prepared.question, numbered)):
            text = splitter.feed(piece)
            if text:
                sent.append(text)
                yield "token", {"text": text}
    except Exception as exc:
        reason = "provider_limited" if provider_limited(exc) else "model_failed"
        log.warning("chat_failed", reason=reason, error=type(exc).__name__)
        yield "error", {"reason": reason}
        return

    rest, suggestions = splitter.finish()
    if rest:
        sent.append(rest)
        yield "token", {"text": rest}
    cited, unknown = citations("".join(sent), set(range(1, len(sources) + 1)))
    if unknown:
        log.info("chat_unknown_citations", count=unknown)
    yield "done", {"citations": cited, "suggestions": suggestions}
