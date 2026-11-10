## 1. Storage

- [x] 1.1 Add models `ChatSession` and `ChatMessage` in `backend/app/db/models/chat.py` (export in `models/__init__.py`) and Alembic revision `0004` creating `chat_sessions` and `chat_messages` (FK cascade, index on `(session_id, id)`, jsonb `sources`/`citations`/`suggestions`), with downgrade; update `docs/database-schema.md`. Verify: `make migrate` upgrades and downgrades on a fresh database, and a model/migration consistency test (as for the other tables) passes.

## 2. Sessions service and endpoints

- [x] 2.1 Add `backend/app/services/chat_sessions.py` (no FastAPI imports): create, list with total and message count, get with messages, rename, delete, `save_question` (inserts the user message, sets the auto title when still "New chat", bumps `updated_at`), `save_answer`, and `stored_history(session, session_id)` (last 6 messages as complete done/stopped pairs with text, truncated to 2000 characters). Verify with integration tests against Postgres: order of list, count, cascade delete, auto title only once and not over a rename, rename keeps `updated_at`, history skips failed pairs and truncates.
- [x] 2.2 Add `backend/app/schemas/chat_sessions.py` and `backend/app/api/v1/chat_sessions.py` (`POST/GET /sessions`, `GET/PATCH/DELETE /sessions/{id}`, 404 `session_not_found`, 422 for blank or over-long title, `limit` 1 to 100) and register in `app/main.py` before the chat router so `/sessions` is not read as another path. Verify with API tests: every scenario of the Sessions and Rename requirements, 401 with a wrong key.

## 3. Saving through chat

- [x] 3.1 Add `session_id` to `ChatRequest`; in `api/v1/chat.py` check the session exists (404 before streaming), save the question and read the stored history in the retrieval database session, and use that history instead of the body's. Verify with API tests: unknown id gives 404 and stores nothing, no `session_id` stores nothing, the rewrite sees stored messages when `history` is empty, and the body's history is ignored.
- [x] 3.2 Wrap the event stream so the assistant message is saved when it ends: collect text, sources, citations, suggestions and rewritten question from the events; `done` → `done`, `error` → `failed`, closed early → `stopped` (nothing saved when no text); the save runs in a shielded task with its own database session and a failure is logged without changing the events. Verify with API/service tests using the fake chat model: completed, model failure after tokens, generator closed after tokens (stopped with partial text), closed before any token (nothing saved), save failure still streams `done`.
- [x] 3.3 Update `docs/api.md` (sessions endpoints, `session_id`, events unchanged, errors) and `docs/security.md` (stored text, shared by key holders, deletion cascades, logs unchanged); `openspec validate add-chat-sessions --strict` passes. Verify the sections match the tests.

## 4. Proxy

- [x] 4.1 In `frontend/src/lib/proxy.ts` allow `DELETE` only for `chat/sessions/<uuid>` (also its GET, POST, PATCH already allowed through `chat`). Verify with proxy tests: delete forwarded with the key, delete of another path is 404 and not forwarded, uuid check rejects `..` and non-uuid.

## 5. Chat page

- [x] 5.1 Add `frontend/src/lib/chatSessions.ts`: typed calls through `/api/backend/chat/sessions` (list, create, get, rename, delete) and the mapping from stored messages to the page's `Turn`; add `session_id` to `chatStream`. Verify with Vitest: mapping of a stored user/assistant pair with sources, a `stopped` and a `failed` message, and `session_id` sent in the request.
- [x] 5.2 Add `SessionList` in `frontend/src/components/` (list, New chat, in-place rename with Enter/Escape/blank, inline delete confirmation, empty and error states with Retry, behind a button on narrow screens). Verify with component tests: every scenario of the Session list, Rename and Delete requirements.
- [x] 5.3 Change `ChatView` and `app/chat/page.tsx` to use `?session=<id>` (Suspense around `useSearchParams`): create a session on the first question, send `session_id`, update the list locally and refetch it when the turn ends, load and show a saved session (stopped note, failed with Retry, not-found state), New chat, stop the stream before switching. Verify with component tests: first question creates a session and sets the address, reload restores answers with chips and source lists, continue appends, switching during a stream stops it, unknown session shows not found.
- [x] 5.4 Update `docs/frontend.md`, `docs/testing.md`, README (feature line; the "no stored conversations" limit becomes "conversations are stored in plain text, shared by everyone with the key"), and `docs/ai-disclosure.md` where it says chat stores nothing. Verify `make lint` and `make test` pass.

## 6. Check in the running stack and finish

- [x] 6.1 With the stack up and a key set: ask two questions in a new chat, reload (both come back with chips and sources), rename the session, press Stop mid-answer and reopen it (partial text, marked stopped), start a second chat, delete the first. Verify the list order, titles and the database rows match what the page showed; look at `/chat` in a browser once (with the user's permission) for the list layout on wide and narrow widths.
- [x] 6.2 Run `make check` and `openspec validate --all --strict`. Verify both are green.
