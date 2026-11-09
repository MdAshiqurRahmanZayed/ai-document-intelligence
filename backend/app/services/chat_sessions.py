"""Stored chat conversations. No FastAPI imports."""

import asyncio
import uuid
from collections.abc import AsyncGenerator, AsyncIterator, Callable, Sequence
from dataclasses import dataclass
from typing import Any

import structlog
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.chat import DEFAULT_TITLE, ChatMessage, ChatSession
from app.llm.chat import Turn

log = structlog.get_logger()

TITLE_FROM_QUESTION = 60
HISTORY_MESSAGES = 6  # the last three turns
HISTORY_CHARS = 2000


@dataclass(frozen=True)
class SessionRow:
    session: ChatSession
    message_count: int


def title_from(question: str) -> str:
    return " ".join(question.split())[:TITLE_FROM_QUESTION] or DEFAULT_TITLE


async def create_session(session: AsyncSession, title: str | None = None) -> SessionRow:
    row = ChatSession(title=(title or DEFAULT_TITLE).strip() or DEFAULT_TITLE)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return SessionRow(row, 0)


async def list_sessions(
    session: AsyncSession, limit: int, offset: int
) -> tuple[list[SessionRow], int]:
    count = (
        select(func.count(ChatMessage.id))
        .where(ChatMessage.session_id == ChatSession.id)
        .scalar_subquery()
    )
    rows = await session.execute(
        select(ChatSession, count)
        .order_by(ChatSession.updated_at.desc(), ChatSession.id)
        .limit(limit)
        .offset(offset)
    )
    total = await session.scalar(select(func.count(ChatSession.id)))
    return [SessionRow(s, n) for s, n in rows.all()], total or 0


async def get_session_with_messages(
    session: AsyncSession, session_id: uuid.UUID
) -> tuple[ChatSession, list[ChatMessage]] | None:
    row = await session.get(ChatSession, session_id)
    if row is None:
        return None
    messages = await session.scalars(
        select(ChatMessage).where(ChatMessage.session_id == session_id).order_by(ChatMessage.id)
    )
    return row, list(messages)


async def exists(session: AsyncSession, session_id: uuid.UUID) -> bool:
    return await session.get(ChatSession, session_id) is not None


async def rename_session(
    session: AsyncSession, session_id: uuid.UUID, title: str
) -> SessionRow | None:
    row = await session.get(ChatSession, session_id)
    if row is None:
        return None
    row.title = title  # updated_at is not touched: a rename must not reorder the list
    await session.commit()
    count = await session.scalar(
        select(func.count(ChatMessage.id)).where(ChatMessage.session_id == session_id)
    )
    return SessionRow(row, count or 0)


async def delete_session(session: AsyncSession, session_id: uuid.UUID) -> bool:
    result = await session.execute(delete(ChatSession).where(ChatSession.id == session_id))
    await session.commit()
    return bool(result.rowcount)  # type: ignore[attr-defined]


async def save_question(session: AsyncSession, session_id: uuid.UUID, question: str) -> None:
    """Store the question; a session still called "New chat" takes its title from it."""
    session.add(ChatMessage(session_id=session_id, role="user", content=question))
    await session.execute(
        update(ChatSession)
        .where(ChatSession.id == session_id, ChatSession.title == DEFAULT_TITLE)
        .values(title=title_from(question))
    )
    await _touch(session, session_id)
    await session.commit()


async def save_answer(
    session: AsyncSession,
    session_id: uuid.UUID,
    *,
    text: str,
    status: str,
    sources: list[dict[str, Any]],
    citations: list[int],
    suggestions: list[str],
    rewritten_question: str | None,
) -> None:
    session.add(
        ChatMessage(
            session_id=session_id,
            role="assistant",
            content=text,
            sources=sources,
            citations=citations,
            suggestions=suggestions,
            rewritten_question=rewritten_question,
            status=status,
        )
    )
    await _touch(session, session_id)
    await session.commit()


async def _touch(session: AsyncSession, session_id: uuid.UUID) -> None:
    await session.execute(
        update(ChatSession).where(ChatSession.id == session_id).values(updated_at=func.now())
    )


def pair_history(messages: Sequence[ChatMessage]) -> list[Turn]:
    """Complete question-and-answer pairs whose answer finished or was stopped with some text,
    the last few of them, each message cut to the size the rewrite accepts."""
    pairs: list[tuple[ChatMessage, ChatMessage]] = []
    for before, after in zip(messages, messages[1:], strict=False):
        if (
            before.role == "user"
            and after.role == "assistant"
            and after.status in ("done", "stopped")
            and after.content.strip()
        ):
            pairs.append((before, after))
    kept = pairs[-(HISTORY_MESSAGES // 2) :]
    return [(m.role, m.content[:HISTORY_CHARS]) for pair in kept for m in pair]


async def stored_history(session: AsyncSession, session_id: uuid.UUID) -> list[Turn]:
    messages = await session.scalars(
        select(ChatMessage).where(ChatMessage.session_id == session_id).order_by(ChatMessage.id)
    )
    return pair_history(list(messages))


type SessionFactory = Callable[[], AsyncSession]

# A save started while the stream is being closed must not be cancelled with it; the loop only
# keeps weak references to tasks, so hold them until they finish.
_saving: set[asyncio.Task[None]] = set()


async def recorded(
    events: AsyncIterator[tuple[str, dict[str, Any]]],
    factory: SessionFactory,
    session_id: uuid.UUID,
) -> AsyncGenerator[tuple[str, dict[str, Any]]]:
    """The same events, and the answer saved when they end however they end: `done`, an `error`
    or the reader going away (Stop). A failed save is logged and never changes the events."""
    text: list[str] = []
    sources: list[dict[str, Any]] = []
    rewritten: str | None = None
    cited: list[int] = []
    suggestions: list[str] = []
    status = "stopped"  # until the stream says how it ended
    try:
        async for name, body in events:
            if name == "sources":
                sources, rewritten = body["sources"], body.get("rewritten_question")
            elif name == "token":
                text.append(body["text"])
            elif name == "done":
                status, cited, suggestions = "done", body["citations"], body["suggestions"]
            elif name == "error":
                status = "failed"
            yield name, body
    finally:
        answer = "".join(text)
        # A stop before any text has nothing worth keeping; a failure keeps its error for Retry.
        if answer or status != "stopped":
            task = asyncio.ensure_future(
                _save_answer(
                    factory, session_id, answer, status, sources, cited, suggestions, rewritten
                )
            )
            _saving.add(task)
            task.add_done_callback(_saving.discard)
            await asyncio.shield(task)


async def _save_answer(
    factory: SessionFactory,
    session_id: uuid.UUID,
    text: str,
    status: str,
    sources: list[dict[str, Any]],
    citations: list[int],
    suggestions: list[str],
    rewritten_question: str | None,
) -> None:
    try:
        async with factory() as session:
            await save_answer(
                session,
                session_id,
                text=text,
                status=status,
                sources=sources,
                citations=citations,
                suggestions=suggestions,
                rewritten_question=rewritten_question,
            )
    except Exception:
        log.warning("chat_save_failed", exc_info=True)
