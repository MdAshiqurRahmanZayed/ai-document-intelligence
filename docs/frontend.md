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

## How progress is shown

- **Upload percentage** is real: bytes sent over file size, per file and overall (XMLHttpRequest, because `fetch` cannot report upload progress). At 100% the file shows "processing on server" until the API answers.
- **Processing bar** is the share of expected steps that finished, not an estimate of time. Steps: uploaded, reading the file, text recognition (PDFs and images; skipped for spreadsheets and for digital PDFs that go straight to extraction), extracting invoices, done. The detail page shows each step as waiting, running, done or failed, with its duration, the attempt number of a retry, and the error of a failed step.
- A **list row** has no processing history, so it shows a coarse position from its status alone (queued, processing, final state). Open the document for exact steps.
- The API does not report pages done, so text recognition has no per-page percentage.

## How the browser reaches the API

The browser never calls the API directly. It calls the web server's own routes:

- `/api/backend/<path>` forwards to `API_URL/api/v1/<path>` (documents, search, jobs, cross-verify) and `/api/backend/readyz` to `/readyz`. It adds the `X-API-Key` header from the server-side `API_KEY`, passes the status and JSON body through, streams request bodies (large uploads), and returns only the content type from the API's headers. Other paths and methods get 404.
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

If something looks wrong: `docker compose logs api worker web`, the Flower Tasks page for the failing task, and the document's `events` in `GET /api/v1/documents/{id}`.
