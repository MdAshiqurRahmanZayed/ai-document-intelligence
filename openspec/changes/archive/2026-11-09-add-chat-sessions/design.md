## Context

`add-chat` keeps turns in React state and sends the last 3 turns as `history`; the server stores nothing. The chat endpoint releases its database session before streaming (the model call can take seconds), and `stream_answer` yields `sources`, `token`\*, `done` | `error`. The project has no accounts, so a session cannot belong to a person. Tables follow `backend/app/db/models/*` (SQLAlchemy 2, Alembic revisions `000n`), and `docs/database-schema.md` must be updated with any model.

## Goals / Non-Goals

**Goals:**
- A conversation survives reload and can be reopened, renamed and deleted.
- What the page shows after reopening equals what it showed live: text, source rows, chips, follow-ups.
- Stored history, not browser history, feeds the rewrite, so one session behaves the same from any browser.

**Non-Goals:** accounts, search, export, editing messages (proposal, Out of Scope).

## Decisions

**Two tables.** `chat_sessions(id uuid pk, title varchar(100), created_at, updated_at)` and `chat_messages(id bigint pk, session_id fk → chat_sessions ON DELETE CASCADE, role 'user'|'assistant', content text, sources jsonb, citations jsonb, suggestions jsonb, rewritten_question text null, status varchar(10), created_at)`, index on `(session_id, id)`. One row per message, assistant rows carry the extras (null on user rows). `status` is `done`, `stopped` or `failed` on assistant rows, null on user rows. Alternative: one row per turn (question + answer); rejected because a question saved before streaming would need a half-empty row and the history for the rewrite reads naturally as messages. `sources` is a JSON snapshot (n, document_id, filename, page_no, quote), not a foreign key: the answer stays readable if the document is later deleted (the link then 404s, which the page already handles for documents). `updated_at` is bumped on every saved message and drives list order.

**Sessions are created explicitly; chat takes `session_id`.** `POST /api/v1/chat/sessions` (optional `title`, default "New chat") returns the session. The page creates one when the first question is asked in an empty chat, then posts the question with `session_id`. Without `session_id`, chat is unchanged and stores nothing, which keeps the existing tests, `docs/api.md` examples and any script working. An unknown `session_id` is 404 `session_not_found`, before streaming.

**Save around the stream, in its own database sessions.** Before streaming, in the same short database session that retrieves chunks, the user message is inserted and, when the session is still titled "New chat", the title is set from the question (first 60 characters, whitespace collapsed). History for the rewrite is read there too: the last 6 stored messages that are not `failed`, before the new question, instead of the request's `history` (the field stays accepted and is ignored when `session_id` is present). When the stream ends, the assistant message is inserted with its own short database session. The save runs in a `finally` around the event generator, so `done`, `error` and the client dropping the connection (Stop) all save, with status `done`, `failed` or `stopped` and whatever text had been produced; a stop with no text saves nothing. A cancelled generator cannot await freely, so the save is started as a task that the `finally` does not cancel (`asyncio.shield`), and a failure to save is logged and never turns a good answer into an error event. A stored turn without an assistant row (server crash mid-stream) is shown as a question with no answer; it is not repaired.

**Failed answers are kept but not used as history.** A `failed` message is stored so the page can show the error and offer Retry; the rewrite history skips it and any user message directly before a failed one would otherwise be a dangling question, so history takes only complete user→assistant pairs (`done` or `stopped` with text).

**Titles: first question, then rename.** No model call. `PATCH /api/v1/chat/sessions/{id}` with `{"title": ...}`: trimmed, 1 to 100 characters, blank is 422. Rename does not change `updated_at`, so renaming does not reorder the list.

**Endpoints.** `GET /sessions?limit=50&offset=0` (limit 1 to 100) returns `{items: [{id, title, created_at, updated_at, message_count}], total}`, newest `updated_at` first. `GET /sessions/{id}` returns the session and `messages` in order. `DELETE /sessions/{id}` returns 204 and cascades. All under the API-key dependency like every `/api/v1` path. No `GET` of messages with paging: a session is a few dozen messages; paging is added if that stops being true.

**Page.** `ChatView` becomes the conversation for one session; a `SessionList` sits in a left column on wide screens (above the conversation, collapsed behind a button, below the `lg` width). The open session is `?session=<id>` (read with `useSearchParams`, which needs a Suspense boundary in the page). Opening loads `GET /sessions/{id}` and maps stored messages to the same `Turn` shape the live stream uses, so one renderer shows both. New chat clears the parameter. Rename is in place (edit icon → input, Enter saves, Escape cancels, blank keeps the old title); delete asks for confirmation inline, not with `window.confirm`. Streaming a turn does not reload the list; it updates the open session's row locally (title after the first question, moved to top) and refetches the list once the turn ends. Switching session while streaming stops the stream first (the same abort as Stop, so the partial answer is saved as `stopped`).

**Proxy.** `DELETE` is allowed only when the path is `chat/sessions/<uuid>`; every other resource keeps GET, POST and PATCH. This is an added requirement in `web-api-access`, because the existing requirement is being modified by the unarchived `add-chat`.

**Privacy.** The database now holds question and answer text. Logs still hold none (unchanged); `docs/security.md` says sessions are stored in plain text, shared by everyone with the key, and deleted by `DELETE` (cascade). Deleting a document does not edit sessions that quote it.

## Risks / Trade-offs

- [Everyone with the key sees every session] → No accounts exist; stated in README and security notes. A per-browser id would be a fake boundary, so none is added.
- [A dropped connection could lose the answer] → Save in `finally` through a shielded task; test with a generator closed after some tokens.
- [Saving fails after a good stream] → Logged, stream unaffected; the page shows the answer live but it is missing on reload. Acceptable for a local tool; surfaced in logs.
- [Stored `sources` quotes drift from the document after reprocessing] → They are a snapshot of what the model was given, which is what a citation should show.
- [Session list grows without limit] → Paged list; manual delete; expiry out of scope.
- [Rewrite history differs from before (stored, not browser)] → Same size cap (6 messages, 2000 characters each, truncated when read).

## Migration Plan

Alembic revision `0004` creates both tables; nothing existing changes. Downgrade drops them. `docs/database-schema.md` is updated in the same change.

## Open Questions

- Should deleting a session also be offered as "delete all"? Not planned; add if the list becomes tedious.
