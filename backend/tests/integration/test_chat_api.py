import json
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DocumentStatus
from app.services.chat import NOTHING_FOUND
from tests.fake_chat import FakeChatModel
from tests.fake_embedder import FakeEmbedder
from tests.helpers import Api
from tests.search_samples import indexed

URL = "/api/v1/chat"


def parse(body: str) -> list[tuple[str, dict[str, Any]]]:
    events = []
    for block in body.strip().split("\n\n"):
        name, data = block.split("\n")
        events.append((name.removeprefix("event: "), json.loads(data.removeprefix("data: "))))
    return events


def with_model(api: Api, model: FakeChatModel) -> FakeChatModel:
    api.app.state.chat_model = model
    api.app.state.embedder = FakeEmbedder()
    return model


async def test_a_question_streams_sources_tokens_and_done(api: Api, session: AsyncSession) -> None:
    await indexed(session, "Cirrus Cloud Services hosting EV-1011", name="cirrus.pdf")
    with_model(api, FakeChatModel(["Cirrus [1].", "\n---FOLLOW-UPS---\nWhat is the total?"]))

    response = await api.client.post(URL, json={"question": "cirrus hosting"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache, no-transform"
    events = parse(response.text)
    assert [name for name, _ in events] == ["sources", "token", "done"]
    assert events[0][1]["sources"][0]["filename"] == "cirrus.pdf"
    assert events[-1][1] == {"citations": [1], "suggestions": ["What is the total?"]}


async def test_nothing_found_answers_without_calling_the_model(
    api: Api, session: AsyncSession
) -> None:
    await indexed(session, "Cirrus hosting", embedded=False)
    model = with_model(api, FakeChatModel(["unused"]))

    response = await api.client.post(URL, json={"question": "zebra"})

    events = parse(response.text)
    assert events[1] == ("token", {"text": NOTHING_FOUND}) and model.stream_calls == []


async def test_history_is_rewritten_and_kept_away_from_the_answer(
    api: Api, session: AsyncSession
) -> None:
    await indexed(session, "Invoice EV-1011 tax 25.00", name="tax.pdf")
    model = with_model(api, FakeChatModel(["25 [1]"], rewritten="tax EV-1011"))
    history = [{"role": "user", "content": "Tell me about EV-1011"}]

    response = await api.client.post(URL, json={"question": "and its tax?", "history": history})

    assert parse(response.text)[0][1]["rewritten_question"] == "tax EV-1011"
    (question, sources) = model.stream_calls[0]
    assert question == "tax EV-1011"
    assert "Tell me about" not in " ".join(text for _, text in sources)


async def test_filters_narrow_the_sources(api: Api, session: AsyncSession) -> None:
    await indexed(session, "an invoice", name="done.pdf", status=DocumentStatus.COMPLETED)
    await indexed(session, "an invoice", name="review.pdf", status=DocumentStatus.NEEDS_REVIEW)
    with_model(api, FakeChatModel(["ok"]))

    response = await api.client.post(
        URL, params={"status": "NEEDS_REVIEW"}, json={"question": "invoice"}
    )

    sources = parse(response.text)[0][1]["sources"]
    assert [s["filename"] for s in sources] == ["review.pdf"]


@pytest.mark.parametrize(
    "body",
    [
        {"question": ""},
        {"question": "   "},
        {},
        {"question": "x" * 1001},
        {"question": "q", "history": [{"role": "user", "content": "m"}] * 7},
        {"question": "q", "history": [{"role": "system", "content": "m"}]},
        {"question": "q", "history": [{"role": "user", "content": "m" * 2001}]},
    ],
)
async def test_invalid_requests_are_422_and_call_no_model(api: Api, body: dict[str, Any]) -> None:
    model = with_model(api, FakeChatModel(["unused"]))

    response = await api.client.post(URL, json=body)

    assert response.status_code == 422
    assert model.rewrite_calls == [] and model.stream_calls == []


async def test_six_history_messages_are_accepted(api: Api) -> None:
    with_model(api, FakeChatModel(["ok"], rewritten="q"))
    history = [{"role": "user", "content": "m"}] * 6

    response = await api.client.post(URL, json={"question": "q", "history": history})

    assert response.status_code == 200


async def test_without_a_model_chat_is_unavailable(api: Api) -> None:
    api.app.state.chat_model = None

    response = await api.client.post(URL, json={"question": "hello"})

    assert response.status_code == 409
    assert response.json() == {"detail": {"reason": "chat_unavailable"}}
