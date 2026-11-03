# Tasks

Verification that needs Docker (compose, e2e) is run by the user; the task says which command. Everything else runs in `frontend/` with `npm test`, `npm run lint`, `npm run typecheck`.

## 1. Flower monitoring

- [x] 1.1 Add `flower` (pinned release) to `backend/pyproject.toml`, refresh the lockfile, and verify `uv sync` resolves and `make lint` still passes
- [x] 1.2 Add `-E` to the worker command in `docker-compose.yml`; verify `docker compose config` shows it
- [x] 1.3 Add the `flower` service (profile `monitoring`, loopback port, basic auth from `FLOWER_USER`/`FLOWER_PASSWORD`, depends on Redis; the start command exits with a clear message when either is unset, because `:?` interpolation would break a plain `make up`); verify the compose file parses and the user sees the message with `docker compose --profile monitoring up flower` and no credentials
- [ ] 1.4 Add `FLOWER_USER`, `FLOWER_PASSWORD` (placeholder), `FLOWER_PORT` to `.env.example`, and a `make flower` target that starts the dashboard and prints its address; verify `make help` lists it
- [ ] 1.5 Document Flower in `docs/monitoring.md` (address, variables, what it shows, what it does not keep) and link it from the README section on running the stack; user verifies with `make up`, `make flower`, upload a file, and the task appears at http://localhost:5555 behind the login

## 2. Frontend foundation

- [x] 2.1 Add dependencies (`@tanstack/react-query`, `react-hook-form`, `zod`, `@hookform/resolvers`, `react-dropzone`, `react-pdf`); read the relevant Next docs under `node_modules/next/dist/docs/` for route handlers and `cacheComponents`; verify `npm ci`, `npm run typecheck` and the existing 3 tests pass
- [x] 2.2 Implement the proxy route handler `app/api/backend/[...path]/route.ts` (fixed `/api/v1/` prefix, GET/POST/PATCH, adds `X-API-Key` from `API_KEY`, streams bodies, passes status and JSON through, 502 when unreachable, no redirects, no upstream headers copied back) with Vitest tests for key added, key absent, error pass-through, 502, and a disallowed path
- [x] 2.3 Add `lib/api.ts` (typed functions from `docs/api.md`, money as strings, `ApiError` from the three error shapes) and `lib/messages.ts` (reason and finding codes to sentences); verify tests cover each error shape and every reason and finding code in `docs/api.md` has a message
- [x] 2.4 Add the query provider, app layout with navigation and the existing readiness badges, `/` redirect to `/documents`, and `API_URL`/`API_KEY` runtime variables in `docker-compose.yml`, `frontend/Dockerfile` and `.env.example` (server only); verify typecheck and a Vitest test that the built client code does not contain the key variable name
- [x] 2.5 Build `components/ui/`: Button, Input and Select with label and error, Table, Modal (focus trap, Escape), Spinner, Progress, Toast provider, EmptyState, ErrorState with retry, and extend `StatusBadge` for document statuses; verify component tests for each (rendering, error text, Modal keyboard behavior, Progress aria values)

## 3. Upload with progress

- [x] 3.1 Implement `lib/upload.ts` with XMLHttpRequest, one request per file, three at a time, reporting bytes sent per file and overall, mapping the per-file API result; verify Vitest tests with a fake XHR for percentages, "sent, waiting", per-file failure not stopping others, and all-request failure keeping files
- [x] 3.2 Implement client file checks (extension list, empty, over the size limit from a constant matching `MAX_UPLOAD_MB`); verify tests for each refusal reason and that refused files are never sent
- [x] 3.3 Build the `/upload` page: dropzone, file list with remove, per-file progress bars and an overall bar, result rows with links and readable reasons, double-submit guard; verify component tests for drop, remove, mixed results, and no second request on double submit

## 4. Documents list and progress

- [x] 4.1 Implement `processingProgress(document, events?)` as a pure function per design decision 3 (steps, percent, current label, failed step, finished state); verify a table-driven test for the cases in the web-document-review spec (scanned in progress 40%, spreadsheet 50%, queued floor, failed step, retry attempt, finished)
- [x] 4.2 Build the `/documents` page: table with status badge, progress bar for unfinished rows, invoice summaries, filters kept in the query string, load more with the cursor, empty/error/loading states; verify component tests for filter request parameters, load more without repeats, and the empty state link to upload
- [x] 4.3 Add adaptive polling (2 s while any listed document is in progress, none otherwise); verify a fake-timer test that the list refreshes and the badge updates, then stops refetching once all are final

## 5. Document detail, corrections, reprocess

- [x] 5.1 Build the `/documents/[id]` shell: header, steps sequence from events (waiting, running, done, failed, duration, attempt), error code and message, 404 state, polling while in progress; verify tests for failed step display and 404
- [x] 5.2 Add the file route `app/api/files/[id]` (server fetches the API's signed link and streams the file, Range passed on, UUID check, nosniff and sandbox headers) and the file viewer: `react-pdf` (lazy, no SSR, worker set in the rendering module) for PDFs, `<img>` for images, download link for spreadsheets; verify unit tests for the route (done) and a component test per file kind, and the user checks that a PDF and an image display next to the result
- [x] 5.3 Render invoices read-only: fields, line items, confidence and source quote, findings with severity text and colour, field marking, duplicate link, document-level findings, not-extracted state; verify tests for several invoices, error marks the field, severity shown as text, duplicate link
- [x] 5.4 Add the correction form (react-hook-form + zod, dirty fields only, `edited_by` name remembered locally, save disabled when unchanged, 422 mapped to the field, 409 busy message, updated invoice and status shown after saving, correction history list); verify tests for each scenario in the web-document-review spec "Correct values"
- [x] 5.5 Add reprocess: confirm modal with from-start or extraction-only choice and the warning about corrections, hidden for busy documents, messages for `extraction_disabled` and `no_text`; verify tests for failed document flow, busy document, and the 409 reasons

## 6. Review queue and search

- [x] 6.1 Build `/review`: `NEEDS_REVIEW` list with findings count, `FAILED` list with error code, retry-all with confirmation and "N queued, M not queued" result, empty state; verify component tests for both lists, retry-all result and the empty state
- [x] 6.2 Build `/search`: query box, mode toggle (hybrid default), filters, address-held state, results with status, page, snippet and invoice summary, `mode_used` notice, `semantic_unavailable` message with keyword offer, no request for a blank query; verify component tests for each scenario in the web-search spec
- [x] 6.3 Implement the safe snippet renderer (split on `<mark>`, render text and `<mark>` elements, never inject HTML); verify a test with a snippet containing a script tag and other markup around a highlighted word

## 7. End to end, docs, integration

- [x] 7.1 Add Playwright (dev dependency, `playwright.config.ts`, `make e2e` target that installs Chromium once and runs against the running stack) with one spec against the Compose stack without a Gemini key: upload a generated CSV, see the percentage and final state, open the document (download link, no viewer), find it by keyword search; user verifies with `make up` then `make e2e`
- [x] 7.2 Write `docs/frontend.md` (routes, data flow, the proxy and key handling, progress meaning, polling, env variables, how to run and test) and update `docs/testing.md` (what Vitest and Playwright cover, what only the real Gemini run covers) and the README run section; verify each documented command runs as written
- [ ] 7.3 Verify the whole change: `make check` (backend and frontend tests, lint, typecheck) passes, `openspec validate --all --strict` passes, a file over 10 MB uploads through the proxy, the bundle contains no API key, and walk the journey by hand with Flower open; record results in the PR description
