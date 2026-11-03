import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Path, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.corrections import CorrectionRequest, CorrectionsOut, build_corrections
from app.schemas.documents import DocumentOut, UploadItem, UploadResponse
from app.schemas.reprocess import ReprocessOut, ReprocessRequest
from app.schemas.results import InvoiceOut, ResultOut, build_result, invoice_out
from app.services.corrections import (
    DocumentBusy,
    InvalidCorrection,
    InvoiceNotFound,
    correct_invoice,
)
from app.services.documents import get_document, ingest_upload
from app.services.errors import DocumentNotFound
from app.services.reprocess import (
    AlreadyQueued,
    CannotReprocess,
    QueueUnavailable,
    reprocess_document,
)
from app.services.results import load_corrections, load_invoice_issues, load_results

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.session_factory() as session:
        yield session


@router.post("", status_code=202, response_model=UploadResponse)
async def upload_documents(
    request: Request,
    files: Annotated[list[UploadFile], File()],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UploadResponse:
    # Always 202 for a well-formed request; each file reports its own outcome.
    state = request.app.state
    max_bytes = state.settings.max_upload_mb * 1024 * 1024
    results = [
        await ingest_upload(
            session=session,
            storage=state.storage,
            enqueue=state.enqueue,
            filename=upload.filename or "unnamed",
            fileobj=upload.file,
            max_bytes=max_bytes,
        )
        for upload in files
    ]
    return UploadResponse(
        results=[
            UploadItem(
                filename=r.filename,
                status=r.status,
                document_id=r.document_id,
                reason=r.reason,
            )
            for r in results
        ]
    )


@router.get("/{document_id}", response_model=DocumentOut)
async def read_document(
    document_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DocumentOut:
    document = await get_document(session, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return DocumentOut.model_validate(document)


@router.get("/{document_id}/result", response_model=ResultOut)
async def read_result(
    document_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ResultOut:
    document = await get_document(session, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    extractions, issues = await load_results(session, document_id)
    return build_result(document, extractions, issues)


@router.patch("/{document_id}/invoices/{invoice_index}", response_model=InvoiceOut)
async def correct(
    document_id: uuid.UUID,
    invoice_index: Annotated[int, Path(ge=0)],
    body: CorrectionRequest,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> InvoiceOut:
    try:
        extraction = await correct_invoice(
            session,
            document_id,
            invoice_index,
            body.fields,
            body.edited_by or "api",
            datetime.now(UTC).date(),
            request.app.state.settings.low_confidence_threshold,
        )
    except DocumentNotFound as exc:
        raise HTTPException(status_code=404, detail="Document not found") from exc
    except InvoiceNotFound as exc:
        raise HTTPException(status_code=404, detail="Invoice not found") from exc
    except DocumentBusy as exc:
        raise HTTPException(status_code=409, detail={"reason": "document_busy"}) from exc
    except InvalidCorrection as exc:
        raise HTTPException(
            status_code=422, detail={"field": exc.field, "message": exc.message}
        ) from exc
    return invoice_out(extraction, await load_invoice_issues(session, extraction.id))


@router.get("/{document_id}/corrections", response_model=CorrectionsOut)
async def read_corrections(
    document_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CorrectionsOut:
    if await get_document(session, document_id) is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return build_corrections(await load_corrections(session, document_id))


@router.post("/{document_id}/reprocess", status_code=202, response_model=ReprocessOut)
async def reprocess(
    document_id: uuid.UUID,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    body: ReprocessRequest | None = None,
) -> ReprocessOut:
    state = request.app.state
    try:
        result = await reprocess_document(
            session,
            document_id,
            (body or ReprocessRequest()).from_stage,
            extraction_enabled=state.settings.google_api_key is not None,
            enqueue=state.enqueue,
            enqueue_extract=state.enqueue_extract,
        )
    except DocumentNotFound as exc:
        raise HTTPException(status_code=404, detail="Document not found") from exc
    except AlreadyQueued as exc:
        raise HTTPException(status_code=409, detail={"reason": "already_queued"}) from exc
    except CannotReprocess as exc:
        raise HTTPException(status_code=409, detail={"reason": exc.reason}) from exc
    except QueueUnavailable as exc:
        raise HTTPException(status_code=503, detail={"reason": "queue_unavailable"}) from exc
    return ReprocessOut(
        document_id=result.document_id, status=result.status, from_stage=result.from_stage
    )

