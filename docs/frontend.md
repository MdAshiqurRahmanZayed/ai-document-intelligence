# Frontend

A Next.js (App Router) + TypeScript + Tailwind v4 interface over the API. Components are our own, in `frontend/src/components/ui/`. Data fetching uses TanStack Query; forms use react-hook-form with zod.

## Pages

| Route | What it does |
|---|---|
| `/documents` | Every document, newest first, with status badge, progress bar, invoice summary. Filters (status, supplier, invoice number, dates, amounts, currency) live in the address. "Load more" pages with the API cursor. Refreshes every 2 s only while a document is unfinished. |
| `/upload` | Drag or browse several files. Each is checked in the browser (type, empty, size), sent one request per file with its own percentage, then shown as accepted, already uploaded or rejected with a link to the document. |
| `/documents/[id]` | The original (PDF viewer one page at a time, image, or a download for TIFF and spreadsheets) beside the extracted invoice(s). Processing steps, validation findings (marked on their field), correction form, correction history, reprocess. |
| `/review` | Documents in `NEEDS_REVIEW` with their findings count, and `FAILED` documents with the reason. Tick rows (or the header box) in the Failed table and press "Retry selected" to retry only those, each from the step that failed. "Retry all failed" asks first and reports how many were queued. |
| `/search` | Keyword, semantic or hybrid search with the same filters. Query, mode and filters are in the address. |
| `/chat` | Ask a question and read an answer built from your documents. The answer streams in; each `[n]` in it is a numbered chip that shows the quote of source n, and the source list (file, page, quote) links to the document. While the answer is written the list shows everything the model is reading; once it is done, only the sources the answer cites (none when it cites nothing). Suggested follow-up questions appear when the answer ends. Each answer sits beside its sources: the answer on the left and a numbered source list on the right (below the answer on a narrow screen), and hovering or focusing a chip highlights its source in the list. The same filters narrow what may be read. Conversations are saved in sessions, listed beside the chat (new chat, open, rename, delete); the open one is in the address (`/chat?session=<id>`), so a reload returns to it. Needs a Google API key. |

## How progress is shown

- **Upload percentage** is real: bytes sent over file size, per file and overall (XMLHttpRequest, because `fetch` cannot report upload progress). At 100% the file shows "processing on server" until the API answers.
- **Processing bar** is the share of expected steps that finished, not an estimate of time. Steps: uploaded, reading the file, text recognition (PDFs and images; skipped for spreadsheets and for digital PDFs that go straight to extraction), extracting invoices, done. The detail page shows each step as waiting, running, done or failed, with its duration, the attempt number of a retry, and the error of a failed step.
- A **list row** has no processing history, so it shows a coarse position from its status alone (queued, processing, final state). Open the document for exact steps.
- The API does not report pages done, so text recognition has no per-page percentage.

## How chat works in the browser

The page posts the question and the session id (and the filters as query parameters) to `/api/backend/chat` with `fetch` (not `EventSource`, which cannot send a body) and reads the response body as it arrives (`lib/chatStream.ts`). The API sends named events:

| Event | What the page does |
|---|---|
| `sources` | Shows the source list at once, before the first word, with "Writing the answer…". Shows "Searched for: …" when the question was rewritten from the history. |
| `token` | Appends the text to the answer. |
| `done` | Shows the suggested follow-ups as buttons that ask them. |
| `error` | Keeps the text so far and says the provider's limit was reached (`provider_limited`) or the answer failed (`model_failed`), with **Try again**. |

- **Citations.** A `[n]` that names a source becomes a chip (hover, focus or click shows the quote); one that names no source is removed, so a made-up number never appears. A chip only means the source was retrieved, not that it proves the sentence: check the quote.
- **Stop** cancels the request (the model call ends with it) and keeps the text so far.
- **Sessions.** The first question in an empty chat creates a session (`POST /api/backend/chat/sessions`), puts its id in the address with `router.replace` and sends every question with `session_id`; the server saves the question and the answer and builds the history for the rewrite from what it stored, so the page sends no history. The list (`components/SessionList.tsx`, loaded by `ChatPage`) shows a new chat at the top at once, titled from the question, and is refreshed when an answer ends.
- **Opening a chat.** `?session=<id>` loads the saved messages (`lib/chatSessions.ts` turns them into the same turns a live stream builds, so one renderer shows both): answers keep their chips and numbered source lists, the last answer its follow-ups; a stopped answer says "Stopped.", a failed one shows its error with **Try again**; an unknown id shows "This chat was not found" with a link to a new chat. Choosing another chat or **New chat** while an answer streams stops it first, so the text so far is saved as stopped.
- **Rename and delete.** Rename is in place (Enter saves, Escape cancels, a blank or unchanged title sends nothing, 100 characters at most; a failed save keeps the old title and says so). Delete asks for confirmation in the list, and leaves the chat if it was open. On a narrow screen the list is behind a **Chats** button.
- **Unavailable.** A 409 `chat_unavailable` shows "Chat is not available: it needs a configured Google API key."
- Text from the answer and the quotes is shown as text; markup in a document cannot run.

## How the browser reaches the API

The browser never calls the API directly. It calls the web server's own routes:

- `/api/backend/<path>` forwards to `API_URL/api/v1/<path>` (documents, search, chat, jobs, cross-verify) and `/api/backend/readyz` to `/readyz`. Only GET, POST and PATCH are forwarded, plus DELETE for `chat/sessions/<uuid>`. It adds the `X-API-Key` header from the server-side `API_KEY`, passes the status and JSON body through, streams request bodies (large uploads), and returns only the content type from the API's headers. A chat answer is a `text/event-stream`: it is passed through as it is written, with `cache-control: no-cache, no-transform` and `x-accel-buffering: no` so nothing holds it back. Other paths and methods get 404.
- `/api/files/<document id>` shows or downloads the original. The server asks the API for the signed storage link, fetches it itself, and streams the bytes back (range requests supported). The browser therefore needs no access to the storage host and no CORS. Responses carry `nosniff` and `Content-Security-Policy: sandbox`.

| Variable | Where | Meaning |
|---|---|---|
| `API_URL` | web container, set in `docker-compose.yml` (`http://api:8000`) | Where the web server reaches the API. For `npm run dev` on the host use `API_URL=http://localhost:8000`. |
| `API_KEY` | `.env`, read by the API and passed to the web container | The shared key. It exists only on the servers; a test checks the source never reads it anywhere else, and the built bundle does not contain it. |

## Run

```bash
make up                  # stack including the web app
# http://localhost:3000  (redirects to /documents)
```

Frontend only, with the stack's API already running:

```bash
cd frontend
npm install
API_URL=http://localhost:8000 API_KEY=<your key, if set> npm run dev
```

## Test

| Command | What it runs |
|---|---|
| `make test` | Backend pytest and the frontend Vitest suite (in Docker) |
| `make check` | Lint, typecheck and all tests, backend and frontend |
| `cd frontend && npm test` | Vitest only, on the host |
| `make e2e` | One Playwright journey against the running stack (`make up` first; installs Chromium once) |

What each layer covers is in [testing.md](testing.md).

## Manual test from the browser

Start with `make up` and `make migrate`, then open http://localhost:3000. Keep `make flower` open at http://localhost:5555 to watch the worker ([monitoring.md](monitoring.md)).

**Without a Google API key** (ingest, OCR and keyword search work; extraction and embeddings do not):

1. **Upload** (`/upload`): drop a PDF, a JPG, an XLSX and a CSV together. Each shows a percentage bar, then "Accepted" with a **View** link. Drop `notes.docx` as well: it is refused in the browser with a reason and is not sent. Drop the same PDF again: "Already uploaded".
2. **Watch it process** (`/documents`): the new rows show a progress bar and step name; the badge changes to Completed by itself (no reload). Flower shows the `ingest` (and `ocr`) tasks.
3. **Open a document**: a PDF appears in the viewer with Previous/Next; an image appears as an image; a spreadsheet shows "cannot be previewed" and a download link. The steps list shows each step with its duration. No invoice form appears, because extraction is off ("No invoice was extracted").
4. **Search** (`/search`): search for a word that is in one of the files with the Keyword mode: the file appears with the word highlighted. Choose Semantic: a message explains it needs a key. Hybrid says it used keyword results.
5. **Failures**: upload a truncated or renamed file (for example a text file renamed `.pdf`): the API rejects it. For a corrupt but valid-looking PDF the document ends `FAILED`; open `/review` to see why, tick the document and press **Retry selected** (or use **Retry all failed**).

**With a Google API key** in `.env` (then `docker compose up -d api worker`):

6. **Extraction**: upload an invoice PDF. The bar passes through "Extracting invoices", the status becomes Completed or Needs review, and the invoice form appears beside the file with confidence and the quoted source text under each value.
7. **Validation**: an invoice whose total does not equal subtotal plus tax shows an Error finding and a red total input; the document is in `/review` with "1 error".
8. **Correct a value**: change the total, press **Save correction**. The finding disappears, the status updates, and **Correction history** shows who changed what. Type `abc` in an amount: the form refuses it before sending.
9. **Reprocess**: press Reprocess, choose "Extraction only", confirm. The document goes back through the steps. Note the warning: the model's values become current again.
10. **Semantic search**: after a minute (embedding runs in the background), search by meaning, for example "when must this be paid" and compare Keyword and Semantic.
11. **Chat** (`/chat`): ask "which supplier invoiced hosting?". The source list appears first, then the answer streams in with numbered chips; hover a chip to see the quote (its source is highlighted in the list on the right) and click a source to open the document. Click a suggested follow-up (the "Searched for" line shows the question rewritten from the saved messages). Reload the page: both questions and answers come back with their chips and sources. Rename the chat in the list, press **Stop** during an answer and reopen the chat (the partial text is there, marked stopped), start a **New chat**, then delete the first one. Ask about something that is not in the documents: the answer says it found nothing and no source list appears. Press **Stop** during an answer to keep what was written.

If something looks wrong: `docker compose logs api worker web`, the Flower Tasks page for the failing task, and the document's `events` in `GET /api/v1/documents/{id}`.
