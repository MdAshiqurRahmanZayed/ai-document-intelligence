from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.documents import get_session
from app.schemas.cross_verify import CrossVerifyRequest, CrossVerifyResponse, build_response
from app.services.cross_verify import DocumentNotFound, NotExtracted, cross_verify

router = APIRouter(prefix="/api/v1/cross-verify", tags=["cross-verify"])


@router.post("", response_model=CrossVerifyResponse)
async def cross_verify_documents(
    body: CrossVerifyRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CrossVerifyResponse:
    if body.left_document_id == body.right_document_id:
        raise HTTPException(status_code=422, detail="Choose two different documents")
    try:
        pairs = await cross_verify(session, body.left_document_id, body.right_document_id)
    except DocumentNotFound as exc:
        raise HTTPException(status_code=404, detail="Document not found") from exc
    except NotExtracted as exc:
        raise HTTPException(
            status_code=409,
            detail={"reason": "not_extracted", "document_id": str(exc.document_id)},
        ) from exc
    return build_response(pairs)
