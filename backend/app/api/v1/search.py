from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.documents import get_session
from app.api.v1.filters import document_filters
from app.schemas.search import SearchOut, build_search
from app.services.listing import DocumentFilters
from app.services.search import Mode, SemanticUnavailable, search

router = APIRouter(prefix="/api/v1/search", tags=["search"])


@router.get("", response_model=SearchOut)
async def search_documents(
    request: Request,
    q: Annotated[str, Query(min_length=1, max_length=500)],
    filters: Annotated[DocumentFilters, Depends(document_filters)],
    session: Annotated[AsyncSession, Depends(get_session)],
    mode: Mode = "hybrid",
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> SearchOut:
    if not q.strip():
        raise HTTPException(status_code=422, detail="q must not be blank")
    try:
        outcome = await search(session, q, mode, filters, limit, request.app.state.embedder)
    except SemanticUnavailable as exc:
        raise HTTPException(status_code=409, detail={"reason": "semantic_unavailable"}) from exc
    return build_search(outcome)
