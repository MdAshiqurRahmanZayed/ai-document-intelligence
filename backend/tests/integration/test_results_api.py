import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, Extraction, ValidationIssue
from tests.helpers import Api, make_document


def extraction(document: Document, **overrides: object) -> Extraction:
    fields: dict[str, object] = {
        "document_id": document.id,
        "invoice_index": 0,
        "version": 1,
        "data": {"invoice_number": "INV-1", "total": "120.00"},
        "field_confidence": {"invoice_number": 0.9},
        "grounding": {"invoice_number": "Invoice INV-1"},
        "model": "test-model",
        "prompt_version": "v1",
    }
    fields.update(overrides)
    return Extraction(**fields)


def issue(document: Document, extraction_id: uuid.UUID | None, code: str) -> ValidationIssue:
    return ValidationIssue(
        document_id=document.id,
        extraction_id=extraction_id,
        code=code,
        field=None,
        severity="error",
        message=code,
    )


async def stored(session: AsyncSession) -> Document:
    document = make_document(status="NEEDS_REVIEW")
    session.add(document)
    await session.commit()
    return document


async def test_an_extracted_document_returns_its_invoices_and_findings(
    api: Api, session: AsyncSession
) -> None:
    document = await stored(session)
    first, second = extraction(document), extraction(document, invoice_index=1)
    session.add_all([first, second])
    await session.commit()
    session.add_all(
        [issue(document, first.id, "total_mismatch"), issue(document, None, "no_invoice_found")]
    )
    await session.commit()

    response = await api.client.get(f"/api/v1/documents/{document.id}/result")

    assert response.status_code == 200
    body = response.json()
    assert (body["document_id"], body["status"]) == (str(document.id), "NEEDS_REVIEW")
    assert [i["invoice_index"] for i in body["invoices"]] == [0, 1]
    one = body["invoices"][0]
    assert one["data"]["total"] == "120.00" and one["model"] == "test-model"
    assert one["field_confidence"] == {"invoice_number": 0.9}
    assert [e["code"] for e in one["validation_errors"]] == ["total_mismatch"]
    assert body["invoices"][1]["validation_errors"] == []
    assert [e["code"] for e in body["document_errors"]] == ["no_invoice_found"]


async def test_only_the_current_version_is_returned(api: Api, session: AsyncSession) -> None:
    document = await stored(session)
    old = extraction(document, is_current=False)
    new = extraction(document, version=2)
    session.add_all([old, new])
    await session.commit()
    session.add(issue(document, old.id, "from_the_old_version"))
    await session.commit()

    body = (await api.client.get(f"/api/v1/documents/{document.id}/result")).json()

    assert [i["version"] for i in body["invoices"]] == [2]
    assert body["invoices"][0]["validation_errors"] == []


async def test_a_document_without_extractions_returns_an_empty_list(
    api: Api, session: AsyncSession
) -> None:
    document = await stored(session)

    response = await api.client.get(f"/api/v1/documents/{document.id}/result")

    assert response.status_code == 200
    assert response.json()["invoices"] == []


async def test_an_unknown_document_is_404(api: Api) -> None:
    response = await api.client.get(f"/api/v1/documents/{uuid.uuid4()}/result")

    assert response.status_code == 404


async def test_a_malformed_id_is_422(api: Api) -> None:
    response = await api.client.get("/api/v1/documents/not-a-uuid/result")

    assert response.status_code == 422
