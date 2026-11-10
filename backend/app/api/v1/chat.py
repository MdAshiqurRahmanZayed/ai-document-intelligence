import json
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.api.v1.filters import document_filters
from app.llm.chat import Turn
from app.schemas.chat import ChatRequest
from app.services import chat_sessions
from app.services.chat import Event, prepare, stream_answer
from app.services.listing import DocumentFilters

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])


def server_event(event: Event) -> str:
    name, body = event
    return f"event: {name}\ndata: {json.dumps(body)}\n\n"


async def server_events(events: AsyncIterator[Event]) -> AsyncIterator[str]:
    async for event in events:
        yield server_event(event)


@router.post("")
async def chat(
    request: Request,
    body: ChatRequest,
    filters: Annotated[DocumentFilters, Depends(document_filters)],
) -> StreamingResponse:
    model = request.app.state.chat_model
    if model is None:
        raise HTTPException(status_code=409, detail={"reason": "chat_unavailable"})
    factory = request.app.state.session_factory
    history: list[Turn] = [(m.role, m.content) for m in body.history]
    # The database is used only to find what to read; it is released before the model writes.
    async with factory() as session:
        if body.session_id is not None:
            if not await chat_sessions.exists(session, body.session_id):
                raise HTTPException(status_code=404, detail={"reason": "session_not_found"})
            # The stored messages replace what the browser sent.
            history = await chat_sessions.stored_history(session, body.session_id)
            await chat_sessions.save_question(session, body.session_id, body.question)
        prepared = await prepare(
            session, model, request.app.state.embedder, body.question, history, filters
        )
    events = stream_answer(model, prepared)
    if body.session_id is not None:
        events = chat_sessions.recorded(events, factory, body.session_id)
    return StreamingResponse(
        server_events(events),
        media_type="text/event-stream",
        # A proxy must not hold the stream back until it ends.
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )
