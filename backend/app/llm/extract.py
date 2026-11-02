"""Reads invoices from page text with a Gemini model. No FastAPI imports."""

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol

import structlog
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable, RunnableLambda
from langchain_google_genai import ChatGoogleGenerativeAI

from app.core.config import Settings
from app.schemas.invoice import ExtractionResult, InvoiceDraft

log = structlog.get_logger()

PROMPT_VERSION = "v1"
_PROMPT_FILE = (
    Path(__file__).resolve().parents[2] / "prompts" / PROMPT_VERSION / "extract_invoice.md"
)
MODEL_TIMEOUT_SECONDS = 90

Page = tuple[int, str]  # page number, text


class ExtractionError(Exception):
    """The model answered, but its answer could not be used."""


@dataclass(frozen=True)
class ExtractedInvoice:
    draft: InvoiceDraft
    text: str  # the pages it was read from: grounding checks the draft against exactly this
    model: str


class InvoiceExtractor(Protocol):
    """What the extraction service needs from a model: the invoices found in some pages."""

    def extract(self, pages: Sequence[Page]) -> list[ExtractedInvoice]: ...


def windows(pages: Sequence[Page], size: int) -> Iterator[Sequence[Page]]:
    for start in range(0, len(pages), size):
        yield pages[start : start + size]


def _render(pages: Sequence[Page]) -> str:
    return "\n\n".join(f"[Page {number}]\n{text}" for number, text in pages)


class Extractor:
    """Sends the pages of a document to the model in windows and collects the invoices."""

    def __init__(self, chain: Runnable[Any, Any], model: str, pages_per_call: int) -> None:
        # The chain takes {"text": ...} and returns {"raw": message, "parsed": ExtractionResult}.
        self._chain = chain
        self._model = model
        self._pages_per_call = pages_per_call

    def extract(self, pages: Sequence[Page]) -> list[ExtractedInvoice]:
        found: list[ExtractedInvoice] = []
        # A blank page has nothing to read; a document with no text makes no model call at all.
        readable = [(number, text) for number, text in pages if text.strip()]
        for window in windows(readable, self._pages_per_call):
            text = _render(window)
            output = self._chain.invoke({"text": text})
            raw, result = output["raw"], output["parsed"]
            # The model that answered can be the fallback, so it is read from the answer.
            model = (getattr(raw, "response_metadata", None) or {}).get("model_name", self._model)
            log.info(
                "extraction_call",
                model=model,
                first_page=window[0][0],
                last_page=window[-1][0],
                invoices=len(result.invoices),
                tokens=getattr(raw, "usage_metadata", None),  # input, output and total tokens
            )
            found.extend(ExtractedInvoice(draft, text, model) for draft in result.invoices)
        return found


@lru_cache
def _system_prompt() -> str:
    return _PROMPT_FILE.read_text(encoding="utf-8")


def build_prompt() -> ChatPromptTemplate:
    # The pages sit between fixed tags and the system prompt says everything inside them is
    # data, not instructions: that is the prompt-injection guard.
    return ChatPromptTemplate.from_messages(
        [("system", _system_prompt()), ("human", "<document>\n{text}\n</document>")]
    )


def ensure_parsed(output: Any) -> Any:
    """Turn a parsing failure into an error, so that retry and fallback react to it.

    `with_structured_output(include_raw=True)` reports a bad answer in the result instead of
    raising; without this step a malformed answer would be accepted as "no invoices".
    """
    if output.get("parsing_error") is not None or output.get("parsed") is None:
        raise ExtractionError(
            f"the model's answer could not be parsed: {output.get('parsing_error')}"
        )
    return output


def _chain(settings: Settings, model: str) -> Runnable[Any, Any]:
    llm = ChatGoogleGenerativeAI(
        model=model,
        google_api_key=settings.google_api_key,
        temperature=0,  # the same page should give the same answer
        timeout=MODEL_TIMEOUT_SECONDS,
        max_retries=1,
    )
    structured = llm.with_structured_output(ExtractionResult, include_raw=True)
    return (build_prompt() | structured | RunnableLambda(ensure_parsed)).with_retry(
        stop_after_attempt=2
    )


def build_extractor(settings: Settings) -> Extractor:
    """The extractor for the configured models: the primary one with the fallback behind it."""
    if settings.google_api_key is None:
        raise ValueError("GOOGLE_API_KEY is not set")
    primary = _chain(settings, settings.gemini_extraction_model)
    fallback = _chain(settings, settings.gemini_fallback_model)
    return Extractor(
        primary.with_fallbacks([fallback]),
        settings.gemini_extraction_model,
        settings.extraction_pages_per_call,
    )
