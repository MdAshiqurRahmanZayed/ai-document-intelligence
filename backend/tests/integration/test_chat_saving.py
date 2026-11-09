import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.chat import ChatMessage, ChatSession
from app.services import chat_sessions as svc
from app.services.chat import NOTHING_FOUND
from tests.fake_chat import FakeChatModel
from tests.fake_embedder import FakeEmbedder
from tests.helpers import Api
from tests.integration.test_chat_api import parse
from tests.search_samples import indexed

URL = "/api/v1/chat"


def with_model(api: Api, model: FakeChatModel) -> FakeChatModel:
    api.app.state.chat_model = model
    api.app.state.embedder = FakeEmbedder()
    return model


async def new_session(api: Api) -> str:
    return (await api.client.post(f"{URL}/sessions")).json()["id"]  # type: ignore[no-any-return]


async def messages(api: Api, session_id: str) -> list[dict[str, Any]]:
    return (await api.client.get(f"{URL}/sessions/{session_id}")).json()["messages"]  # type: ignore[no-any-return]


async def test_question_and_answer_are_saved_with_what_the_page_needs(
    api: Api, session: AsyncSession
) -> None:
    await indexed(session, "Cirrus Cloud Services hosting EV-1011", name="cirrus.pdf")
    with_model(api, FakeChatModel(["Cirrus [1].", "\n---FOLLOW-UPS---\nWhat is the total?"]))
    sid = await new_session(api)

    response = await api.client.post(URL, json={"question": "cirrus hosting", "session_id": sid})

    assert [n for n, _ in parse(response.text)] == ["sources", "token", "done"]
    user, assistant = await messages(api, sid)
    assert (user["role"], user["content"]) == ("user", "cirrus hosting")
    assert assistant["content"] == "Cirrus [1]."
    assert assistant["status"] == "done" and assistant["citations"] == [1]
    assert assistant["suggestions"] == ["What is the total?"]
    assert assistant["sources"][0]["filename"] == "cirrus.pdf"
    detail = (await api.client.get(f"{URL}/sessions/{sid}")).json()
    assert detail["title"] == "cirrus hosting" and detail["message_count"] == 2


async def test_nothing_found_is_saved_too(api: Api, session: AsyncSession) -> None:
    await indexed(session, "Cirrus hosting", embedded=False)
    with_model(api, FakeChatModel(["unused"]))
    sid = await new_session(api)

    await api.client.post(URL, json={"question": "zebra", "session_id": sid})

    _, assistant = await messages(api, sid)
    assert assistant["content"] == NOTHING_FOUND and assistant["sources"] == []


async def test_model_failure_keeps_the_text_so_far_as_failed(
    api: Api, session: AsyncSession
) -> None:
    await indexed(session, "Cirrus hosting EV-1011")
    with_model(api, FakeChatModel(["Cirrus "], error=RuntimeError("boom")))
    sid = await new_session(api)

    response = await api.client.post(URL, json={"question": "cirrus hosting", "session_id": sid})

    assert parse(response.text)[-1][0] == "error"
    _, assistant = await messages(api, sid)
    assert assistant["status"] == "failed" and assistant["content"] == "Cirrus "


async def test_unknown_session_is_404_and_stores_nothing(api: Api, session: AsyncSession) -> None:
    model = with_model(api, FakeChatModel(["x"]))

    response = await api.client.post(URL, json={"question": "hi", "session_id": str(uuid.uuid4())})

    assert response.status_code == 404
    assert response.json()["detail"] == {"reason": "session_not_found"}
    assert model.stream_calls == []
    assert await session.scalar(select(func.count(ChatMessage.id))) == 0


async def test_without_a_session_nothing_is_stored(api: Api, session: AsyncSession) -> None:
    await indexed(session, "Cirrus hosting EV-1011")
    with_model(api, FakeChatModel(["Cirrus [1]."]))

    response = await api.client.post(URL, json={"question": "cirrus hosting"})

    assert response.status_code == 200
    assert await session.scalar(select(func.count(ChatSession.id))) == 0
    assert await session.scalar(select(func.count(ChatMessage.id))) == 0


async def test_the_rewrite_reads_stored_messages_and_ignores_the_body(
    api: Api, session: AsyncSession
) -> None:
    await indexed(session, "Invoice EV-1011 tax 25.00", name="tax.pdf")
    model = with_model(api, FakeChatModel(["25 [1]"], rewritten="tax EV-1011"))
    sid = await new_session(api)
    await api.client.post(URL, json={"question": "Tell me about EV-1011", "session_id": sid})
    model.rewrite_calls.clear()

    response = await api.client.post(
        URL,
        json={
            "question": "and its tax?",
            "session_id": sid,
            "history": [{"role": "user", "content": "from the browser"}],
        },
    )

    assert parse(response.text)[0][1]["rewritten_question"] == "tax EV-1011"
    history, question = model.rewrite_calls[0]
    assert question == "and its tax?"
    assert history[0] == ("user", "Tell me about EV-1011")
    assert "from the browser" not in str(history)


async def test_a_failed_answer_is_not_part_of_the_history(api: Api, session: AsyncSession) -> None:
    await indexed(session, "Invoice EV-1011 tax 25.00")
    model = with_model(api, FakeChatModel(["a"], error=RuntimeError("boom")))
    sid = await new_session(api)
    await api.client.post(URL, json={"question": "tax EV-1011", "session_id": sid})
    model.error, model.pieces = None, ["fine [1]"]
    model.rewritten = "tax EV-1011"
    model.rewrite_calls.clear()

    await api.client.post(URL, json={"question": "tax EV-1011 again", "session_id": sid})

    assert model.rewrite_calls == []  # no complete pair, so no history and no rewrite


async def events_from(items: list[tuple[str, dict[str, Any]]]):  # type: ignore[no-untyped-def]
    for item in items:
        yield item


async def test_closing_the_stream_early_saves_the_partial_answer_as_stopped(
    api: Api, session: AsyncSession
) -> None:
    sid = uuid.UUID((await api.client.post(f"{URL}/sessions")).json()["id"])
    stream = svc.recorded(
        events_from(
            [
                ("sources", {"sources": [], "rewritten_question": "q?"}),
                ("token", {"text": "Part"}),
                ("token", {"text": "ial"}),
                ("done", {"citations": [], "suggestions": []}),
            ]
        ),
        api.app.state.session_factory,
        sid,
    )
    await anext(stream)
    await anext(stream)
    await anext(stream)
    await stream.aclose()  # the reader went away after "Part" and "ial"

    (assistant,) = (await session.scalars(select(ChatMessage))).all()
    assert (assistant.status, assistant.content) == ("stopped", "Partial")
    assert assistant.rewritten_question == "q?"


async def test_closing_before_any_text_saves_nothing(api: Api, session: AsyncSession) -> None:
    sid = uuid.UUID((await api.client.post(f"{URL}/sessions")).json()["id"])
    stream = svc.recorded(
        events_from([("sources", {"sources": []}), ("token", {"text": "x"})]),
        api.app.state.session_factory,
        sid,
    )
    await anext(stream)
    await stream.aclose()

    assert await session.scalar(select(func.count(ChatMessage.id))) == 0


async def test_a_failing_save_does_not_change_the_events(api: Api) -> None:
    def broken() -> Any:
        raise RuntimeError("database gone")

    events: list[tuple[str, dict[str, Any]]] = [
        ("sources", {"sources": []}),
        ("token", {"text": "ok"}),
        ("done", {"citations": [], "suggestions": []}),
    ]

    seen = [e async for e in svc.recorded(events_from(events), broken, uuid.uuid4())]

    assert [n for n, _ in seen] == ["sources", "token", "done"]
