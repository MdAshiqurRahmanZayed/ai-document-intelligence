from sqlalchemy.ext.asyncio import AsyncSession

from app.services.chat import prepare
from app.services.listing import DocumentFilters
from tests.fake_chat import FakeChatModel
from tests.fake_embedder import FakeEmbedder
from tests.search_samples import indexed

NO_FILTERS = DocumentFilters()
HISTORY = [("user", "Tell me about EV-1011"), ("assistant", "It is from Cirrus [1].")]


async def test_without_history_there_is_no_rewrite(session: AsyncSession) -> None:
    await indexed(session, "Cirrus Cloud Services invoice EV-1011 hosting", name="cirrus.pdf")
    model = FakeChatModel(rewritten="should not be used")

    prepared = await prepare(session, model, FakeEmbedder(), "cirrus hosting", [], NO_FILTERS)

    assert model.rewrite_calls == []
    assert prepared.question == "cirrus hosting" and prepared.rewritten is False
    assert [c.filename for c in prepared.chunks] == ["cirrus.pdf"]


async def test_history_is_rewritten_and_the_rewrite_is_used_to_retrieve(
    session: AsyncSession,
) -> None:
    await indexed(session, "Invoice EV-1011 tax 25.00", name="tax.pdf")
    await indexed(session, "Something else entirely", name="other.pdf")
    model = FakeChatModel(rewritten="tax EV-1011")

    prepared = await prepare(session, model, FakeEmbedder(), "and its tax?", HISTORY, NO_FILTERS)

    assert model.rewrite_calls == [(HISTORY, "and its tax?")]
    assert prepared.rewritten is True
    assert prepared.question == "tax EV-1011"
    assert [c.filename for c in prepared.chunks] == ["tax.pdf"]


async def test_a_failed_rewrite_falls_back_to_the_original_question(
    session: AsyncSession,
) -> None:
    await indexed(session, "Cirrus hosting", name="cirrus.pdf")
    model = FakeChatModel(fail_rewrite=True)

    prepared = await prepare(session, model, FakeEmbedder(), "cirrus", HISTORY, NO_FILTERS)

    assert prepared.question == "cirrus" and prepared.rewritten is False
    assert [c.filename for c in prepared.chunks] == ["cirrus.pdf"]


async def test_nothing_relevant_gives_no_chunks(session: AsyncSession) -> None:
    await indexed(session, "Cirrus hosting invoice", embedded=False)

    prepared = await prepare(session, FakeChatModel(), FakeEmbedder(), "zebra", [], NO_FILTERS)

    assert prepared.chunks == []
