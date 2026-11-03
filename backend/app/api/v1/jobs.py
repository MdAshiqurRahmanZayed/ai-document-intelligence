from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.documents import get_session
from app.schemas.reprocess import RetryFailedOut
from app.services.reprocess import retry_failed

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])


@router.post("/retry-failed", response_model=RetryFailedOut)
async def retry_failed_documents(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
) -> RetryFailedOut:
    state = request.app.state
    result = await retry_failed(
        session,
        limit,
        extraction_enabled=state.settings.google_api_key is not None,
        enqueue=state.enqueue,
        enqueue_extract=state.enqueue_extract,
    )
    return RetryFailedOut(queued=result.queued, not_queued=result.not_queued)
