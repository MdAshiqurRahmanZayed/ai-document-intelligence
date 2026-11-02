import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.documents import DocumentOut, UploadItem, UploadResponse
from app.services.documents import get_document, ingest_upload

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
