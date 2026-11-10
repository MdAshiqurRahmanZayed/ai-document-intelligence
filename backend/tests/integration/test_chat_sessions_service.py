import asyncio

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.chat import ChatMessage
from app.services import chat_sessions as svc


async def answer(session: AsyncSession, session_id, text: str, status: str = "done") -> None:  # type: ignore[no-untyped-def]
    await svc.save_answer(
        session,
        session_id,
        text=text,
        status=status,
        sources=[{"n": 1, "document_id": "d", "filename": "a.pdf", "page_no": 1, "quote": "q"}],
        citations=[1],
        suggestions=["next?"],
        rewritten_question=None,
    )


async def test_list_is_newest_first_with_counts(session: AsyncSession) -> None:
    first = (await svc.create_session(session)).session
    second = (await svc.create_session(session)).session
    await svc.save_question(session, first.id, "older question")  # moves `first` to the top

    rows, total = await svc.list_sessions(session, 50, 0)

    assert total == 2
    assert [r.session.id for r in rows] == [first.id, second.id]
    assert [r.message_count for r in rows] == [1, 0]


async def test_deleting_a_session_removes_its_messages(session: AsyncSession) -> None:
    row = (await svc.create_session(session)).session
    await svc.save_question(session, row.id, "q")
    await answer(session, row.id, "a")

    assert await svc.delete_session(session, row.id) is True
    assert await svc.delete_session(session, row.id) is False
    assert await session.scalar(select(func.count(ChatMessage.id))) == 0


async def test_first_question_sets_the_title_once_and_never_over_a_rename(
    session: AsyncSession,
) -> None:
    row = (await svc.create_session(session)).session
    await svc.save_question(session, row.id, "  Which   supplier\ninvoiced hosting?  ")
    await session.refresh(row)
    assert row.title == "Which supplier invoiced hosting?"

    await svc.save_question(session, row.id, "another question")
    await session.refresh(row)
    assert row.title == "Which supplier invoiced hosting?"

    await svc.rename_session(session, row.id, "Hosting")
    await svc.save_question(session, row.id, "third")
    await session.refresh(row)
    assert row.title == "Hosting"


async def test_title_is_cut_to_sixty_characters(session: AsyncSession) -> None:
    row = (await svc.create_session(session)).session
    await svc.save_question(session, row.id, "x" * 200)
    await session.refresh(row)
    assert len(row.title) == 60


async def test_rename_keeps_updated_at(session: AsyncSession) -> None:
    row = (await svc.create_session(session)).session
    await svc.save_question(session, row.id, "q")
    await session.refresh(row)
    before = row.updated_at
    await asyncio.sleep(0.01)

    await svc.rename_session(session, row.id, "New name")
    await session.refresh(row)

    assert row.title == "New name" and row.updated_at == before


async def test_history_is_complete_done_or_stopped_pairs_cut_to_size(session: AsyncSession) -> None:
    row = (await svc.create_session(session)).session
    await svc.save_question(session, row.id, "q1")
    await answer(session, row.id, "a1")
    await svc.save_question(session, row.id, "q2 failed")
    await answer(session, row.id, "partial", status="failed")
    await svc.save_question(session, row.id, "q3 no answer")  # crashed: no assistant row
    await svc.save_question(session, row.id, "q4")
    await answer(session, row.id, "z" * 3000, status="stopped")

    history = await svc.stored_history(session, row.id)

    assert [content[:3] for _, content in history] == ["q1", "a1", "q4", "zzz"]
    assert len(history[-1][1]) == 2000


async def test_history_keeps_only_the_last_three_pairs(session: AsyncSession) -> None:
    row = (await svc.create_session(session)).session
    for i in range(5):
        await svc.save_question(session, row.id, f"q{i}")
        await answer(session, row.id, f"a{i}")

    history = await svc.stored_history(session, row.id)

    assert [c for _, c in history] == ["q2", "a2", "q3", "a3", "q4", "a4"]
