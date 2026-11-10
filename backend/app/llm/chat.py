"""Answers questions from the text of documents with a Gemini model. No FastAPI imports."""

import re
from collections.abc import Iterator, Sequence
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol

import structlog
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable
from langchain_google_genai import ChatGoogleGenerativeAI

from app.core.config import Settings

log = structlog.get_logger()

PROMPT_VERSION = "v1"
_PROMPTS = Path(__file__).resolve().parents[2] / "prompts" / PROMPT_VERSION
MODEL_TIMEOUT_SECONDS = 60
ANSWER_MAX_TOKENS = 400
REWRITE_MAX_TOKENS = 150
# The answer ends with this line and then the suggested follow-up questions.
FOLLOW_UPS_DELIMITER = "---FOLLOW-UPS---"

Source = tuple[int, str]  # number, text of a chunk
Turn = tuple[str, str]  # role, content of an earlier message


class ChatModel(Protocol):
    """What the chat service needs from a model."""

    def rewrite(self, history: Sequence[Turn], question: str) -> str:
        """The question made understandable without the earlier messages."""
        ...

    def stream(self, question: str, sources: Sequence[Source]) -> Iterator[str]:
        """The answer, in pieces, read only from the sources."""
        ...


# The text of a document or an earlier message must not be able to close the tag it sits in.
_FIXED_TAGS = re.compile(r"<(/?)(source|history|question)", re.IGNORECASE)


def _neutralise(text: str) -> str:
    return _FIXED_TAGS.sub(r"[\1\2", text)


def render_sources(sources: Sequence[Source]) -> str:
    return "\n\n".join(
        f'<source n="{number}">\n{_neutralise(text)}\n</source>' for number, text in sources
    )


def render_history(history: Sequence[Turn]) -> str:
    return "\n".join(f"{role}: {_neutralise(content)}" for role, content in history)


@lru_cache
def _prompt_text(name: str) -> str:
    return (_PROMPTS / name).read_text(encoding="utf-8")


def answer_prompt() -> ChatPromptTemplate:
    # The instructions come first and are the same on every call, so the provider can reuse them.
    return ChatPromptTemplate.from_messages(
        [
            ("system", _prompt_text("chat.md")),
            ("human", "{context}\n\n<question>\n{question}\n</question>"),
        ]
    )


def rewrite_prompt() -> ChatPromptTemplate:
    return ChatPromptTemplate.from_messages(
        [
            ("system", _prompt_text("chat_rewrite.md")),
            ("human", "<history>\n{history}\n</history>\n<question>\n{question}\n</question>"),
        ]
    )


def message_text(message: Any) -> str:
    """The text of a model message; some models answer with a list of parts."""
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content
    return "".join(
        part if isinstance(part, str) else str(part.get("text", ""))
        for part in content
        if isinstance(part, str) or isinstance(part, dict)
    )


class GeminiChat:
    def __init__(self, answer: Runnable[Any, Any], rewrite: Runnable[Any, Any], model: str) -> None:
        # Both chains take a dict and return a message (or message pieces when streamed).
        self._answer = answer
        self._rewrite = rewrite
        self._model = model

    def rewrite(self, history: Sequence[Turn], question: str) -> str:
        message = self._rewrite.invoke({"history": render_history(history), "question": question})
        self._log("rewrite", message, chunks=0, chars=0)
        return message_text(message).strip()

    def stream(self, question: str, sources: Sequence[Source]) -> Iterator[str]:
        total: Any = None
        try:
            for piece in self._answer.stream(
                {"context": render_sources(sources), "question": question}
            ):
                total = piece if total is None else total + piece
                text = message_text(piece)
                if text:
                    yield text
        finally:
            # Logged even when the stream stops early; the model's own counts, never the text.
            self._log("answer", total, chunks=len(sources), chars=sum(len(t) for _, t in sources))

    def _log(self, kind: str, message: Any, *, chunks: int, chars: int) -> None:
        usage = getattr(message, "usage_metadata", None) or {}
        metadata = getattr(message, "response_metadata", None) or {}
        log.info(
            "chat_call",
            kind=kind,
            model=metadata.get("model_name", self._model),
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
            chunks=chunks,
            chars=chars,
        )


def _llm(settings: Settings, model: str, max_tokens: int) -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(
        model=model,
        google_api_key=settings.google_api_key,
        temperature=0,
        timeout=MODEL_TIMEOUT_SECONDS,
        # One retry by the client library. A LangChain retry wrapper is not used: it would
        # turn the stream into a single piece.
        max_retries=1,
        max_output_tokens=max_tokens,
    )


def build_chat_model(settings: Settings) -> GeminiChat:
    """The configured extraction model with the fallback model behind it."""
    if settings.google_api_key is None:
        raise ValueError("GOOGLE_API_KEY is not set")

    def chain(prompt: ChatPromptTemplate, max_tokens: int) -> Runnable[Any, Any]:
        primary = _llm(settings, settings.gemini_extraction_model, max_tokens)
        fallback = _llm(settings, settings.gemini_fallback_model, max_tokens)
        return prompt | primary.with_fallbacks([fallback])

    return GeminiChat(
        chain(answer_prompt(), ANSWER_MAX_TOKENS),
        chain(rewrite_prompt(), REWRITE_MAX_TOKENS),
        settings.gemini_extraction_model,
    )
