import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CrossCheck, Document, Extraction
from app.schemas.invoice import InvoiceData
from tests.helpers import Api, make_document

URL = "/api/v1/cross-verify"


async def document_with_invoice(
    session: AsyncSession, total: str = "120.00", number: str = "INV-7"
) -> Document:
    document = make_document()
    session.add(document)
    await session.commit()
    data = InvoiceData(
        invoice_number=number, supplier_name="Acme Ltd", total=Decimal(total), currency="EUR"
    )
    session.add(
        Extraction(
            document_id=document.id,
            invoice_index=0,
            version=1,
            data=data.to_jsonable(),
            field_confidence={},
            grounding={},
            model="test-model",
            prompt_version="v1",
        )
    )
    await session.commit()
    return document


async def stored_checks(session: AsyncSession) -> int:
    return await session.scalar(select(func.count()).select_from(CrossCheck)) or 0


async def test_two_extracted_documents_are_compared_and_the_result_is_stored(
    api: Api, session: AsyncSession
) -> None:
    pdf = await document_with_invoice(session, total="120.00")
    excel = await document_with_invoice(session, total="125.00")

    response = await api.client.post(
        URL, json={"left_document_id": str(pdf.id), "right_document_id": str(excel.id)}
    )

    assert response.status_code == 200
    (check,) = response.json()["checks"]
    assert check["status"] == "mismatch" and check["match_key"] == "inv7"
    assert check["diffs"] == [{"field": "total", "left": "120.00", "right": "125.00"}]
    assert check["left"]["data"]["total"] == "120.00"
    assert await stored_checks(session) == 1


async def test_equal_invoices_match(api: Api, session: AsyncSession) -> None:
    left, right = await document_with_invoice(session), await document_with_invoice(session)

    response = await api.client.post(
        URL, json={"left_document_id": str(left.id), "right_document_id": str(right.id)}
    )

    (check,) = response.json()["checks"]
    assert (check["status"], check["diffs"]) == ("match", [])


async def test_running_the_same_pair_twice_keeps_only_the_latest_result(
    api: Api, session: AsyncSession
) -> None:
    left, right = await document_with_invoice(session), await document_with_invoice(session)
    body = {"left_document_id": str(left.id), "right_document_id": str(right.id)}

    await api.client.post(URL, json=body)
    await api.client.post(URL, json=body)
    # The same pair the other way round replaces the result as well.
    await api.client.post(
        URL, json={"left_document_id": str(right.id), "right_document_id": str(left.id)}
    )

    assert await stored_checks(session) == 1


async def test_an_unknown_document_is_404(api: Api, session: AsyncSession) -> None:
    known = await document_with_invoice(session)

    response = await api.client.post(
        URL, json={"left_document_id": str(known.id), "right_document_id": str(uuid.uuid4())}
    )

    assert response.status_code == 404


async def test_the_same_document_twice_is_422(api: Api, session: AsyncSession) -> None:
    document = await document_with_invoice(session)

    response = await api.client.post(
        URL, json={"left_document_id": str(document.id), "right_document_id": str(document.id)}
    )

    assert response.status_code == 422


async def test_a_document_without_invoices_is_409_not_extracted(
    api: Api, session: AsyncSession
) -> None:
    extracted = await document_with_invoice(session)
    empty = make_document()
    session.add(empty)
    await session.commit()

    response = await api.client.post(
        URL, json={"left_document_id": str(extracted.id), "right_document_id": str(empty.id)}
    )

    assert response.status_code == 409
    assert response.json()["detail"] == {"reason": "not_extracted", "document_id": str(empty.id)}
