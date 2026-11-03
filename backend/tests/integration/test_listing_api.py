import uuid
from datetime import date

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DocumentStatus
from tests.helpers import Api
from tests.listing_samples import add_document, add_invoice

URL = "/api/v1/documents"


async def test_the_list_pages_through_all_documents_newest_first(
    api: Api, session: AsyncSession
) -> None:
    created = [(await add_document(session, minutes=n)).id for n in range(25)]

    seen: list[str] = []
    sizes: list[int] = []
    url = f"{URL}?limit=10"
    while True:
        body = (await api.client.get(url)).json()
        sizes.append(len(body["items"]))
        seen += [item["id"] for item in body["items"]]
        if body["next_cursor"] is None:
            break
        url = f"{URL}?limit=10&cursor={body['next_cursor']}"

    assert sizes == [10, 10, 5]
    assert seen == [str(i) for i in reversed(created)]


async def test_an_item_has_the_document_fields_and_its_invoice_summary(
    api: Api, session: AsyncSession
) -> None:
    document = await add_document(session)
    await add_invoice(session, document, number="INV-7", total="120.50", currency="EUR")

    (item,) = (await api.client.get(URL)).json()["items"]

    assert item["id"] == str(document.id) and item["status"] == "COMPLETED"
    assert {"filename", "source_type", "page_count", "error_code", "created_at"} <= set(item)
    assert item["invoices"] == [
        {
            "invoice_index": 0,
            "invoice_number": "INV-7",
            "supplier_name": "Acme Industries Ltd.",
            "invoice_date": "2026-01-05",
            "total": "120.5000",
            "currency": "EUR",
        }
    ]


async def test_each_filter_works_through_the_query_string(api: Api, session: AsyncSession) -> None:
    review = await add_document(session, 0, DocumentStatus.NEEDS_REVIEW)
    await add_invoice(session, review, supplier="Acme Ltd", number="INV-7", total="50.00")
    done = await add_document(session, 1)
    await add_invoice(
        session, done, supplier="Globex", number="B-2", total="150.00", currency="USD",
        on=date(2026, 3, 1),
    )  # fmt: skip

    async def found(query: str) -> list[str]:
        items = (await api.client.get(f"{URL}?{query}")).json()["items"]
        return [item["id"] for item in items]

    assert await found("status=NEEDS_REVIEW") == [str(review.id)]
    assert await found("supplier=acme") == [str(review.id)]
    assert await found("invoice_number=inv%207") == [str(review.id)]
    assert await found("date_from=2026-02-01&date_to=2026-12-31") == [str(done.id)]
    assert await found("amount_min=100&amount_max=200") == [str(done.id)]
    assert await found("currency=usd") == [str(done.id)]
    assert await found("currency=USD&amount_max=100") == []


@pytest.mark.parametrize(
    "query",
    [
        "status=NOPE",
        "limit=101",
        "limit=0",
        "cursor=garbage",
        "date_from=yesterday",
        "amount_min=lots",
    ],
)
async def test_bad_parameters_are_422(api: Api, query: str) -> None:
    assert (await api.client.get(f"{URL}?{query}")).status_code == 422


async def test_the_file_link_of_a_stored_document(api: Api, session: AsyncSession) -> None:
    document = await add_document(session)

    response = await api.client.get(f"{URL}/{document.id}/file")

    assert response.status_code == 200
    body = response.json()
    assert body["expires_in"] == 300
    assert document.storage_key in body["url"] and "expires=300" in body["url"]


async def test_the_file_link_of_an_unknown_document_is_404(api: Api) -> None:
    assert (await api.client.get(f"{URL}/{uuid.uuid4()}/file")).status_code == 404
