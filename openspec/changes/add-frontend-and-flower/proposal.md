# Proposal

## Why

The backend does everything the assignment asks (upload, OCR, extraction, validation, corrections, reprocess, search), but a person can only reach it with `curl`. Task 6 requires a web interface to upload documents, watch processing, inspect results, fix values and search. The frontend is also how the real Gemini run will be checked end to end. With workers doing the slow OCR and LLM work, there is currently no quick way to see whether they are alive and what they are running, so Flower is added in the same change to make that investigation possible.

## What Changes

- Next.js pages for the full journey:
  - **Upload** (`/upload`): multi-file dropzone, client checks for type and size, one result row per file.
  - **Documents** (`/documents`): list with status badges, filters, keyset "load more", polling while any document is in progress.
  - **Document detail** (`/documents/[id]`): original file viewer next to the extracted invoice, validation findings per field, processing history, correction form, reprocess button.
  - **Review queue** (`/review`): `NEEDS_REVIEW` documents, plus failed documents with a retry-all button.
  - **Search** (`/search`): keyword, semantic and hybrid modes with the list filters.
- A typed API client and TanStack Query hooks. The browser talks only to Next.js route handlers (`/api/backend/...`) which forward to the API and add the `X-API-Key` header on the server, so the key is never in the browser bundle.
- Our own UI components (Button, Input, Badge, Table, Modal, Spinner, Toast) in `components/ui/`, no UI library.
- Loading, empty and error states on every page.
- Vitest component tests, and one Playwright test of the journey (upload, open result, correct a value).
- **Flower**: a `flower` service in Docker Compose behind the `monitoring` profile, bound to `127.0.0.1`, protected with basic auth from the environment, plus worker task events, a `make flower` target and documentation.

### Out of scope

- Live push (SSE or WebSocket). Pages poll instead.
- Generating the client from OpenAPI.
- User accounts, roles, per-user keys. The one shared API key stays.
- Cross-verification screen (the API stays; no UI unless time remains).
- Bulk edit, dark mode, i18n, mobile layout polish.
- Running Flower in the default `make up`, or exposing it beyond localhost.
- Backend behavior changes. No API endpoint changes are planned.

## Capabilities

### New Capabilities
- `web-api-access`: how the browser reaches the API, with the key kept on the server, and consistent loading, empty and error handling.
- `web-upload`: choosing several files, checking them in the browser, sending them and showing a result for each.
- `web-document-review`: list, detail, validation findings, corrections, reprocess, review queue and failed-document retry.
- `web-search`: the search page with mode toggle, filters and results.
- `worker-monitoring`: Flower for inspecting workers and tasks.

### Modified Capabilities
<!-- None: no existing API requirement changes. -->

## Impact

- `frontend/`: new routes, components, hooks, tests; new dependencies (`@tanstack/react-query`, `react-hook-form`, `zod`, `@hookform/resolvers`, `react-dropzone`, `react-pdf`, dev: `@playwright/test`).
- `docker-compose.yml`, `Makefile`, `.env.example`, `backend/pyproject.toml` and its lockfile (`flower`), worker command (`-E`).
- `docs/`: `docs/frontend.md` (routes, data flow, key handling), `docs/testing.md`, a README note for Flower.
- Frontend image gets runtime variables `API_URL` and `API_KEY` (server only); `NEXT_PUBLIC_API_URL` is no longer needed for data calls.
- CORS: browser calls become same-origin, so the API's `WEB_ORIGIN` allowance is no longer required for the UI (left in place).
