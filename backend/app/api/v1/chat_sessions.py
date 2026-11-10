import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.documents import get_session
from app.schemas.chat_sessions import (
    MessageOut,
    SessionCreate,
    SessionDetail,
    SessionList,
    SessionOut,
    SessionRename,
)
from app.services import chat_sessions as service

router = APIRouter(prefix="/api/v1/chat/sessions", tags=["chat"])

Db = Annotated[AsyncSession, Depends(get_session)]


def not_found() -> HTTPException:
    return HTTPException(status_code=404, detail={"reason": "session_not_found"})


def out(row: service.SessionRow) -> SessionOut:
    s = row.session
    return SessionOut(
        id=s.id,
        title=s.title,
        created_at=s.created_at,
        updated_at=s.updated_at,
        message_count=row.message_count,
    )


@router.post("", status_code=201, response_model=SessionOut)
async def create(session: Db, body: SessionCreate | None = None) -> SessionOut:
    return out(await service.create_session(session, body.title if body else None))


@router.get("", response_model=SessionList)
async def list_all(
    session: Db,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SessionList:
    rows, total = await service.list_sessions(session, limit, offset)
    return SessionList(items=[out(r) for r in rows], total=total)


@router.get("/{session_id}", response_model=SessionDetail)
async def read(session: Db, session_id: uuid.UUID) -> SessionDetail:
    found = await service.get_session_with_messages(session, session_id)
    if found is None:
        raise not_found()
    row, messages = found
    return SessionDetail(
        **out(service.SessionRow(row, len(messages))).model_dump(),
        messages=[MessageOut.model_validate(m) for m in messages],
    )


@router.patch("/{session_id}", response_model=SessionOut)
async def rename(session: Db, session_id: uuid.UUID, body: SessionRename) -> SessionOut:
    row = await service.rename_session(session, session_id, body.title)
    if row is None:
        raise not_found()
    return out(row)


@router.delete("/{session_id}", status_code=204)
async def remove(session: Db, session_id: uuid.UUID) -> Response:
    if not await service.delete_session(session, session_id):
        raise not_found()
    return Response(status_code=204)
