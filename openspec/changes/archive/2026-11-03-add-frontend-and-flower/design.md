# Design

## Context

The API is finished and documented in `docs/api.md`. The frontend today is a health page (`ReadinessPanel`, `StatusBadge`, 3 tests) on Next.js 16 with `output: "standalone"`, `cacheComponents` on, Tailwind v4, and no data libraries. `frontend/AGENTS.md` says this Next.js differs from older versions, so implementation reads `node_modules/next/dist/docs/` before using a Next API. The API needs `X-API-Key` when `API_KEY` is set, and has no endpoint that returns a progress percentage. Workers are one Celery process on queues `ingest,ocr,llm,embed`; the compose `worker` health check already runs `inspect ping`. See proposal.md for motivation.

## Goals / Non-Goals

**Goals:**
- A person can finish the whole journey in a browser: upload, watch, inspect, correct, retry, search.
- Progress that is honest: real bytes for upload, real finished steps for processing.
- The API key never reaches the browser.
- Flower shows worker and task state with one command and no change to the default stack.

**Non-Goals:**
- No backend change. Where the API lacks something (page-level OCR progress), the UI shows what exists.
- No state library beyond TanStack Query; no global store.
- No component library or design system beyond the small set in `components/ui/`.

## Decisions

### 1. Server-side proxy through one route handler
`app/api/backend/[...path]/route.ts` forwards GET, POST and PATCH to `API_URL`, adds `X-API-Key` from `API_KEY`, and streams the request and response bodies. `API_URL` and `API_KEY` are plain server environment variables read at request time, so one image runs anywhere and the key is not inlined into the bundle (unlike `NEXT_PUBLIC_*`).
- *Alternative: call the API from the browser with `NEXT_PUBLIC_API_KEY`.* Rejected: the key would be in every visitor's bundle, against the brief's security line.
- *Alternative: `rewrites()` in `next.config.ts`.* Rejected: rewrites cannot add a secret header per request.
- Side effect: same-origin calls need no CORS. The existing `WEB_ORIGIN` allowance stays for the readiness panel and direct API use.
- Only a route handler is used, no `proxy.ts`. The 10 MB buffering limit in the Next docs (`proxyClientMaxBodySize`) applies only when `proxy.ts` is used, so large uploads stream through. A task verifies this with a file over 10 MB.
- The handler allows only the paths the UI needs (`/api/v1/*`) and drops hop-by-hop headers. It does not follow redirects and never returns upstream headers such as `set-cookie`.
- The file viewer does not load the signed storage link in the browser. The link points at the storage host as the API sees it (`storage:8333` in Compose, not resolvable from a browser) and PDF.js would need CORS on the object store. A second route handler, `app/api/files/[id]`, asks the API for the link (with the key), fetches it on the server and streams the bytes back from our own origin, passing `Range` requests on. The id must be a UUID and the link comes from the API, never from the client, so the client cannot choose what is fetched. Responses carry `nosniff` and `Content-Security-Policy: sandbox`. No backend change and no `S3_PUBLIC_URL` are needed.

### 2. Upload progress with XMLHttpRequest
`fetch` cannot report upload bytes, so each batch uses `XMLHttpRequest` with `upload.onprogress`. One request per file (not one for all) so each file has its own percentage and result, and a failed file does not hide the others. Up to 3 run at once. The overall bar is the sum of sent bytes over total bytes. After the last byte the file shows "processing on server" until the response arrives (the API stores the file before answering, so this can take a moment for large files).
- *Alternative: one multipart request for all files.* Rejected: one percentage for everything, and one failure loses all.
- The API's response is per file already, so one-file requests return a one-element `results` list, merged into the page state.

### 3. Processing progress is derived from status and events
The API returns `status` and `events` (stage, status, attempt, duration) on `GET /documents/{id}`, and a list item has only `status`. The percentage is computed in one pure function `processingProgress(document)` from the expected steps:

| Step | Expected when | Done when |
|---|---|---|
| Uploaded | always | document exists |
| Reading file | always | `ingest` succeeded |
| Text recognition | `ocr` started, or the document has scanned pages / is an image | `ocr` succeeded |
| Extracting invoices | extraction enabled | `extract` succeeded |
| Done | always | status `COMPLETED` or `NEEDS_REVIEW` |

Percent is `finished steps / expected steps`, with a floor of 10% so a queued document does not look stuck. Text recognition counts as expected for PDFs and images until an `extract` event shows the document took the digital path, so a scanned document's percentage never drops; a spreadsheet never expects it. `embed` is not a step: it never changes status and failures there are hidden from this bar (shown only in history). A list row has no events, so it uses a coarser mapping from status (`QUEUED` low, `PROCESSING` middle, final states); the detail page loads events and shows exact steps. Two facts are not in the API today and are decided here: whether text recognition applies (use `source_type` image, or an `ocr` event) and whether extraction is enabled (use the presence of an `extract` event, otherwise assume enabled once `ingest` finished and show "extracting" only while status is `PROCESSING`). This keeps the function simple and honest; if the guess is wrong the bar still ends at 100% on a final status.
- *Alternative: add a progress field to the API (pages read of page_count).* Cleaner, but a backend change; deferred. It would give per-page OCR percentages and is the first follow-up if reviewers want finer progress.
- Polling: TanStack Query `refetchInterval` returns 2 s while any visible document is in progress and `false` otherwise; the detail page polls the same way. Polling pauses in a hidden tab (library default).

### 4. Data layer
`lib/api.ts` holds one typed function per endpoint and a single `ApiError` (status, reason, field, message) built from the API's three error shapes (`detail` string, `detail.reason`, `detail.field + message`). Types are written by hand from `docs/api.md`; money stays a **string** end to end (never `Number`), dates stay ISO strings. TanStack Query hooks (`useDocuments`, `useDocument`, `useResult`, `useSearch`, mutations for upload, correct, reprocess, retry-failed) own caching and invalidation: a correction updates the result and the document and invalidates the list.
- `lib/messages.ts` maps `reason` codes and finding codes to plain sentences (one table, tested).

### 5. Detail page: viewer and form
Split pane: left `react-pdf` for PDFs (loaded only on the detail page, client component, lazy) or an `<img>` for images; spreadsheets show the stored page text via the download link and a note. Right: one card per invoice with the form (react-hook-form + zod). zod schemas check shape only (date format, amount pattern as text, currency three letters); the API stays the authority and its `422 {field, message}` is attached to the field with `setError`. Only dirty fields are sent in the PATCH, `edited_by` comes from a name box remembered in `localStorage` (default "web"). Findings with a `field` render under and mark that input; the list also shows findings without a field.
- `react-pdf` needs its worker set in the same module that renders the pages, and the module must skip server rendering (`next/dynamic` with `ssr: false`). The worker file is bundled from `pdfjs-dist` through `new URL(..., import.meta.url)`.

### 6. Pages and state in the URL
Routes: `/` redirects to `/documents`; `/upload`, `/documents`, `/documents/[id]`, `/review`, `/search`. Filters and search query live in the query string (`useSearchParams`) so views are shareable and survive reload. A shared layout holds the nav and the existing readiness badges. With `cacheComponents` on, pages that read `searchParams` or poll are client components under `Suspense`; the plan is to follow the Next docs for this when coding, not assume older patterns.

### 7. Components
`components/ui/`: Button, Input (with label and error), Select, Badge (reuse and extend `StatusBadge`), Table, Modal (focus trap, Escape), Spinner, Progress, Toast (small provider), EmptyState, ErrorState (with retry). No library: Tailwind classes only. Status colours are always paired with text for accessibility. Snippets are rendered by splitting the safe snippet on `<mark>` / `</mark>` into text and `<mark>` elements, never `dangerouslySetInnerHTML`, so the escaping rule holds even if the API regresses.

### 8. Flower
- Service `flower` in `docker-compose.yml`, `profiles: ["monitoring"]`, `<<: *backend` image, command `celery -A app.workers.celery_app flower --port=5555 --basic-auth=${FLOWER_USER}:${FLOWER_PASSWORD}`, published as `127.0.0.1:${FLOWER_PORT:-5555}:5555`, depends on Redis healthy. The start command checks both variables and exits with a clear message when one is unset. (`${VAR:?}` interpolation was rejected: Compose interpolates the whole file, so it would break a plain `make up` for everyone not using Flower.)
- Worker command gains `-E` so task events are published (without events Flower shows workers but not tasks).
- `flower` is added to `backend/pyproject.toml` and the lockfile; to keep the production image lean it goes in the same dependency group the image already installs (one image serves api, worker and flower), pinned to a released version.
- `make flower` runs `docker compose --profile monitoring up -d flower` after `up` and prints the address. `.env.example` gets `FLOWER_USER`, `FLOWER_PASSWORD` (placeholder, not a real value), `FLOWER_PORT`.
- Flower reads Celery events from Redis only; it adds no persistence (task history is lost when it restarts). Our `processing_events` table remains the durable record.

### 9. Tests
- Vitest + Testing Library: `processingProgress` (table of cases), `ApiError` parsing, `messages`, upload validation, Progress/Badge/Modal components, safe snippet rendering, correction form (only dirty fields sent, 422 mapped to field), list polling on/off with fake timers and a stubbed fetch.
- Playwright (one spec, run in CI against the Compose stack with `GOOGLE_API_KEY` unset, so no real model): upload a small generated CSV, see the percentage bar and final state, open the document, check its pages, search by keyword. The correction journey needs an extracted invoice, which needs the model; it is covered by Vitest with a stubbed API, and is part of the deferred real Gemini run by hand. This is stated in `docs/testing.md`.
- Playwright is a dev dependency with its own `make e2e` target, not part of `make check`, so the default check stays fast.

## Risks / Trade-offs

- [Uploaded files are served from our origin] → `nosniff`, `Content-Security-Policy: sandbox`, UUID-only ids, bytes only from links the API signed.
- [Progress percentage looks precise but is stage-based] → Label says the step name; docs say it is steps finished, not time; a follow-up can add page counts to the API.
- [Route handler becomes an open proxy] → Fixed path prefix `/api/v1/`, only GET/POST/PATCH, no redirects, no upstream headers copied back, and the API still enforces its own key.
- [Large uploads time out in the proxy] → Stream the body; test with a file over 10 MB; the API already reads in 8 MiB chunks.
- [Polling load] → 2 s only while something is in progress, paused in hidden tabs, one request for the whole list not per row.
- [`cacheComponents` and client fetching surprises] → Data pages are client components using TanStack Query; the route handler is dynamic; checked against the Next docs while coding.
- [Flower exposes task arguments, which can include document ids and names] → Loopback only, basic auth, off by default.
- [Playwright flakiness] → One spec, waits on visible state not timers, runs outside `make check`.

## Migration Plan

Additive. Steps: add frontend dependencies and the proxy, build pages, then the Compose and Makefile changes for Flower. The frontend image gains runtime variables `API_URL` (default `http://api:8000`) and `API_KEY`; `NEXT_PUBLIC_API_URL` stays only for the readiness panel until it is switched to the proxy in this change. Rollback is reverting the change; no data or schema is touched.

## Open Questions

1. Name of the "edited by" default ("web" vs asking on first save). Either works with the specs.
