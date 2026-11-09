## Why

The chat page keeps its conversation in the browser only: reload the page and every question and answer is gone, and there is no way to return to an earlier line of questions. People expect what they asked, and what the documents answered, to be kept, found again and named, as in any chat tool.

## What Changes

- New stored **chat sessions**: a session has a title and holds its messages in order. Both the question and the full answer are saved, with what the page needs to show them again: the sources (document, page, quote), the cited numbers, the follow-up suggestions, the stand-alone question and how the answer ended (`done`, `stopped`, `failed`).
- New endpoints under `/api/v1/chat/sessions`: create, list (most recently used first), read with messages, rename, delete.
- `POST /api/v1/chat` takes an optional `session_id`. With it, the server saves the question before streaming, saves the answer when the stream ends (also when the person pressed Stop or the model failed), and builds the history for the question rewrite from the stored messages, not from the browser. Without it, chat works as before and stores nothing.
- A new session is titled from its first question (first 60 characters); a person can rename it (1 to 100 characters).
- `/chat` page gets a session list beside the conversation: new chat, open, rename in place, delete with confirmation. The open session is in the address (`/chat?session=<id>`), so a reload or a shared link returns to it. Opening a session shows every saved message with its sources and chips exactly as when it was answered.
- The web server's proxy also forwards `DELETE`, for chat sessions only.
- **BREAKING (behaviour):** the earlier decision "nothing is stored on the server" no longer holds for sessions. Questions and answers are now kept in the database until deleted, so `docs/security.md` and the README limits change.

## Capabilities

### New Capabilities
- `chat-sessions`: stored sessions and messages, their endpoints, saving through the chat endpoint.
- `web-chat-sessions`: the session list, opening, renaming, deleting and restoring a conversation on the chat page.

### Modified Capabilities
- `web-api-access`: the proxy allows `DELETE` for chat sessions (added requirement; the existing ones are untouched).

## Impact

- Backend: two models (`ChatSession`, `ChatMessage`) and migration `0004`; new `services/chat_sessions.py`, `schemas/chat_sessions.py`, `api/v1/chat_sessions.py`; `schemas/chat.py` and `api/v1/chat.py` take `session_id` and save; router registered in `main.py`. No new setting or dependency.
- Frontend: `ChatView` is split into the conversation and a `SessionList`; a small sessions client in `lib/`; `proxy.ts` allows DELETE for `chat/sessions/*`.
- Docs: `docs/api.md`, `docs/database-schema.md` (required by the project), `docs/frontend.md`, `docs/security.md`, `docs/testing.md`, README (feature, limits).
- Depends on `add-chat` (extends its endpoint, page and specs); archive `add-chat` first.

## Out of Scope

- Accounts and per-person sessions. There is still one shared key: everyone who reaches the web server sees every session. The README and security notes say so.
- Searching inside sessions, pinning, folders, export, sharing links with different rights.
- Editing or regenerating a saved message, branching a conversation.
- Automatic expiry of old sessions; deletion is manual.
- Titles written by the model (an extra call per session on a daily-limited provider).
