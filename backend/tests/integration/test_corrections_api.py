import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DocumentStatus
from tests.helpers import Api
from tests.invoice_fakes import draft, extracted_document

WRONG_TOTAL = draft(total="130.00")


def invoice_url(document_id: uuid.UUID, index: int = 0) -> str:
    return f"/api/v1/documents/{document_id}/invoices/{index}"


async def test_a_patch_returns_the_updated_invoice(api: Api, session: AsyncSession) -> None:
    document = await extracted_document(session, [WRONG_TOTAL])

    response = await api.client.patch(
        invoice_url(document.id), json={"fields": {"total": "120.00"}, "edited_by": "Maria"}
    )

    assert response.status_code == 200
    body = response.json()
    assert (body["invoice_index"], body["version"], body["model"]) == (0, 2, "manual")
    assert body["data"]["total"] == "120.00"
    assert body["field_confidence"]["total"] == 1.0
    assert "total_mismatch" not in [e["code"] for e in body["validation_errors"]]
    result = (await api.client.get(f"/api/v1/documents/{document.id}/result")).json()
    assert result["status"] == DocumentStatus.COMPLETED  # the fix cleared the review


async def test_the_corrections_list_shows_the_changes_newest_first(
    api: Api, session: AsyncSession
) -> None:
    document = await extracted_document(session, [draft()])
    await api.client.patch(invoice_url(document.id), json={"fields": {"currency": "USD"}})
    await api.client.patch(
        invoice_url(document.id), json={"fields": {"total": "125.00"}, "edited_by": "Maria"}
    )

    response = await api.client.get(f"/api/v1/documents/{document.id}/corrections")

    assert response.status_code == 200
    rows = response.json()["corrections"]
    assert [(r["field"], r["old_value"], r["new_value"], r["edited_by"]) for r in rows] == [
        ("total", "120.00", "125.00", "Maria"),
        ("currency", "EUR", "USD", "api"),  # edited_by defaults to "api"
    ]
    assert {r["invoice_index"] for r in rows} == {0}


async def test_an_unknown_document_or_invoice_is_404(api: Api, session: AsyncSession) -> None:
    document = await extracted_document(session, [draft()])
    body = {"fields": {"total": "1"}}

    assert (await api.client.patch(invoice_url(uuid.uuid4()), json=body)).status_code == 404
    assert (await api.client.patch(invoice_url(document.id, 5), json=body)).status_code == 404
    unknown = f"/api/v1/documents/{uuid.uuid4()}/corrections"
    assert (await api.client.get(unknown)).status_code == 404


async def test_a_document_that_is_processing_is_409(api: Api, session: AsyncSession) -> None:
    document = await extracted_document(session, [draft()])
    document.status = DocumentStatus.PROCESSING
    await session.commit()

    response = await api.client.patch(invoice_url(document.id), json={"fields": {"total": "1"}})

    assert response.status_code == 409
    assert response.json()["detail"] == {"reason": "document_busy"}


async def test_an_invalid_patch_is_422_and_names_the_field(api: Api, session: AsyncSession) -> None:
    document = await extracted_document(session, [draft()])

    unknown = await api.client.patch(invoice_url(document.id), json={"fields": {"colour": "red"}})
    unreadable = await api.client.patch(
        invoice_url(document.id), json={"fields": {"total": "lots"}}
    )
    no_fields = await api.client.patch(invoice_url(document.id), json={})
    negative_index = await api.client.patch(invoice_url(document.id, -1), json={"fields": {}})

    assert unknown.status_code == 422 and unknown.json()["detail"]["field"] == "colour"
    assert unreadable.status_code == 422 and unreadable.json()["detail"]["field"] == "total"
    assert no_fields.status_code == 422  # the body needs "fields"
    assert negative_index.status_code == 422
    result = (await api.client.get(f"/api/v1/documents/{document.id}/result")).json()
    assert [i["version"] for i in result["invoices"]] == [1]  # nothing was saved
