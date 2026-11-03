import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DocumentStatus
from tests.fake_embedder import FakeEmbedder
from tests.helpers import Api
from tests.listing_samples import add_invoice
from tests.search_samples import indexed

URL = "/api/v1/search"


async def test_keyword_search_returns_the_documented_shape(api: Api, session: AsyncSession) -> None:
    document = await indexed(session, "Cover", "Acme Industries invoice", name="acme.pdf")
    await add_invoice(session, document, number="INV-7", total="120.00")

    response = await api.client.get(URL, params={"q": "industries acme", "mode": "keyword"})

    assert response.status_code == 200
    body = response.json()
    assert body["mode_used"] == "keyword"
    (result,) = body["results"]
    assert (result["document_id"], result["filename"], result["page_no"]) == (
        str(document.id),
        "acme.pdf",
        2,
    )
    assert result["status"] == "COMPLETED" and result["score"] > 0
    assert "<mark>" in result["snippet"]
    assert result["invoices"][0]["invoice_number"] == "INV-7"


async def test_filters_and_the_limit_apply(api: Api, session: AsyncSession) -> None:
    await indexed(session, "an invoice", name="done.pdf", status=DocumentStatus.COMPLETED)
    await indexed(session, "an invoice", name="review.pdf", status=DocumentStatus.NEEDS_REVIEW)

    filtered = await api.client.get(URL, params={"q": "invoice", "status": "NEEDS_REVIEW"})
    limited = await api.client.get(URL, params={"q": "invoice", "limit": 1})

    assert [r["filename"] for r in filtered.json()["results"]] == ["review.pdf"]
    assert len(limited.json()["results"]) == 1


async def test_markup_in_a_document_cannot_reach_the_client_through_the_snippet(
    api: Api, session: AsyncSession
) -> None:
    await indexed(session, "<script>alert(1)</script> invoice")

    (result,) = (await api.client.get(URL, params={"q": "invoice"})).json()["results"]

    snippet = result["snippet"]
    # PostgreSQL's headline leaves HTML tags out; anything it kept is escaped by the server.
    assert "<script" not in snippet and "</script" not in snippet
    assert "<" not in snippet.replace("<mark>", "").replace("</mark>", "")
    assert "<mark>invoice</mark>" in snippet


async def test_semantic_search_finds_meaning(api: Api, session: AsyncSession) -> None:
    api.app.state.embedder = FakeEmbedder()
    await indexed(session, "bananas are yellow fruit", name="fruit.pdf")
    await indexed(session, "payment is due within thirty days", name="terms.pdf")

    body = (await api.client.get(URL, params={"q": "when must I pay", "mode": "semantic"})).json()

    assert body["mode_used"] == "semantic"
    assert body["results"][0]["filename"] == "terms.pdf"


async def test_semantic_search_without_a_model_is_409(api: Api) -> None:
    response = await api.client.get(URL, params={"q": "pay", "mode": "semantic"})

    assert response.status_code == 409
    assert response.json()["detail"] == {"reason": "semantic_unavailable"}


async def test_hybrid_is_the_default_and_falls_back_to_keyword_without_a_model(
    api: Api, session: AsyncSession
) -> None:
    await indexed(session, "payment due now", name="words.pdf")
    await indexed(session, "settle the owed amount", name="meaning-only.pdf")

    without_model = (await api.client.get(URL, params={"q": "payment due"})).json()
    api.app.state.embedder = FakeEmbedder()
    with_model = (await api.client.get(URL, params={"q": "payment due"})).json()

    assert without_model["mode_used"] == "keyword"
    assert [r["filename"] for r in without_model["results"]] == ["words.pdf"]
    assert with_model["mode_used"] == "hybrid"
    assert [r["filename"] for r in with_model["results"]] == ["words.pdf", "meaning-only.pdf"]


async def test_filters_apply_in_semantic_mode(api: Api, session: AsyncSession) -> None:
    api.app.state.embedder = FakeEmbedder()
    await indexed(session, "payment is due", name="a.pdf", status=DocumentStatus.NEEDS_REVIEW)
    await indexed(session, "payment is due", name="b.pdf", status=DocumentStatus.COMPLETED)

    body = (
        await api.client.get(URL, params={"q": "pay", "mode": "semantic", "status": "COMPLETED"})
    ).json()

    assert [r["filename"] for r in body["results"]] == ["b.pdf"]


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"q": ""},
        {"q": "   "},
        {"q": "invoice", "mode": "fuzzy"},
        {"q": "invoice", "limit": 51},
        {"q": "invoice", "limit": 0},
        {"q": "invoice", "status": "NOPE"},
    ],
)
async def test_bad_requests_are_422(api: Api, params: dict[str, str | int]) -> None:
    assert (await api.client.get(URL, params=params)).status_code == 422
