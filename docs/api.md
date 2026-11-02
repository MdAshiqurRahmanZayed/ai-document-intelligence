# API reference

Base URL (local): `http://localhost:8000`. Interactive docs (generated, always current): `/docs`.

Keep this file in sync with the code whenever an endpoint, field or error reason changes.

## Contents

- [Health](#health)
- [Upload documents](#upload-documents)
- [Get a document](#get-a-document)
- [Reference: statuses, reasons, limits](#reference)

## Health

| Endpoint | Purpose | Success | Failure |
|---|---|---|---|
| `GET /healthz` | Process is alive. Never touches dependencies. | `200 {"status":"ok"}` | n/a |
| `GET /readyz` | Database, Redis and storage are reachable. | `200 {"status":"ok","checks":{"database":"ok","redis":"ok","storage":"ok"}}` | `503` with the failing check set to `"error"` |

`/readyz` never includes hostnames, credentials or exception text; the reason is in the API log.

## Upload documents

`POST /api/v1/documents`, `multipart/form-data`, field name `files` (repeat it for several files).

```bash
curl -F "files=@invoice.pdf" -F "files=@data.csv" localhost:8000/api/v1/documents
```

**Response: `202 Accepted`** whenever the request is well formed. Each file gets its own result, in request order:

```json
{
  "results": [
    { "filename": "invoice.pdf", "status": "accepted",  "document_id": "3f2a…", "reason": null },
    { "filename": "copy.pdf",    "status": "duplicate", "document_id": "3f2a…", "reason": null },
    { "filename": "empty.pdf",   "status": "rejected",  "document_id": null,    "reason": "empty_file" }
  ]
}
```

| Result `status` | Meaning |
|---|---|
| `accepted` | Stored, recorded and queued for processing. `document_id` is set. |
| `duplicate` | Identical bytes (same SHA-256) were uploaded before and that document is not `FAILED`. `document_id` is the existing document; nothing is stored or processed again. |
| `rejected` | Not accepted. `reason` says why (see [reasons](#reference)). |

Other responses: `422` if the request contains no files.

Notes:
- The file type is decided from the file's **contents**, not its name or the client's content type. Accepted: PDF, JPEG, PNG, TIFF, XLSX, XLS, CSV.
- Only exact duplicates are detected here. The same invoice re-scanned or re-saved is a different file.
- A changed file has a different hash, so it is accepted as a new document.
- Uploading the same bytes again retries a document that is `FAILED`: it goes back to `QUEUED`, one new job is queued, and the result is `accepted` with the existing `document_id`. If the queue is still unavailable the result is `rejected` (`queue_unavailable`) and the document stays `FAILED`.

## Get a document

`GET /api/v1/documents/{document_id}`

```bash
curl localhost:8000/api/v1/documents/3f2a…
```

**`200`**

```json
{
  "id": "3f2a…",
  "filename": "invoice.pdf",
  "mime": "application/pdf",
  "size": 48213,
  "status": "COMPLETED",
  "source_type": "pdf",
  "page_count": 2,
  "error_code": null,
  "error_message": null,
  "created_at": "2026-11-02T10:15:00Z",
  "updated_at": "2026-11-02T10:15:02Z",
  "events": [
    { "stage": "ingest", "status": "started",   "attempt": 1, "duration_ms": null, "error_code": null, "error_message": null, "created_at": "…" },
    { "stage": "ingest", "status": "succeeded", "attempt": 1, "duration_ms": 12,   "error_code": null, "error_message": null, "created_at": "…" },
    { "stage": "ocr",    "status": "started",   "attempt": 1, "duration_ms": null, "error_code": null, "error_message": null, "created_at": "…" },
    { "stage": "ocr",    "status": "succeeded", "attempt": 1, "duration_ms": 1840, "error_code": null, "error_message": null, "created_at": "…" }
  ]
}
```

`events` is the processing history, oldest first. `stage` is `ingest` (reading the file and saving its pages) or `ocr` (reading the text of scanned pages and images; only present when a document has such pages). A failed attempt adds a `failed` event; its retry then adds a `started` event with the next `attempt` number.

| Response | When |
|---|---|
| `404` | No document with that id |
| `422` | `document_id` is not a valid UUID |

## Reference

### Document statuses

| Status | Meaning |
|---|---|
| `UPLOADED` | Stored and recorded, not yet handed to the queue (brief) |
| `QUEUED` | Waiting for a worker |
| `PROCESSING` | A worker is running a job. Stays `PROCESSING` between the ingest job and the OCR job when pages need OCR |
| `COMPLETED` | All jobs finished (for files with scanned pages or images: after the OCR job) |
| `NEEDS_REVIEW` | Reserved for validation (later phase) |
| `FAILED` | Job failed after retries, or could not be queued. See `error_code` |

### Rejection reasons (`status: "rejected"`)

| `reason` | Meaning |
|---|---|
| `empty_file` | Zero bytes |
| `file_too_large` | Over `MAX_UPLOAD_MB` (default 100 MB per file) |
| `unsupported_type` | Contents are not one of the accepted types (includes renamed or corrupt files) |
| `storage_error` | Object storage refused the write; no record was created |
| `queue_unavailable` | Stored, but the queue refused the job; the document exists with status `FAILED` and `error_code` `queue_unavailable` |

### Document error codes (`error_code`)

| Code | Meaning |
|---|---|
| `queue_unavailable` | The job could not be queued at upload time |
| `pdf_corrupt` | The PDF is damaged or truncated and cannot be opened. Not retried |
| `pdf_encrypted` | The PDF needs a password. Not retried |
| `pdf_empty` | The PDF opened but has no pages. Not retried |
| `image_corrupt` | The image is damaged, truncated or too large to decode safely. Not retried |
| `spreadsheet_corrupt` | The XLSX, XLS or CSV is damaged and cannot be read. Not retried |
| `spreadsheet_empty` | The spreadsheet opens but no sheet holds any data. Not retried |
| `ingest_failed` | The ingest job failed on every attempt (first try plus 3 retries); `error_message` holds the exception type |
| `ocr_failed` | The OCR job failed on every attempt (first try plus 3 retries); `error_message` holds the exception type |

`page_count` is filled once the file has been opened, so it is already set while the pages are still being read: one per PDF page, one per image frame (a multi-frame TIFF has several), and for a spreadsheet the number of text pages (each sheet with data gives one page per 100 data rows). A spreadsheet document goes straight to `COMPLETED` after the ingest job: it never has an `ocr` stage.

### Limits

- `MAX_UPLOAD_MB` (env, default 100): per file.
- Files are read in 8 MiB chunks, so memory use does not grow with file size.
- No limit yet on files per request, and no authentication or rate limiting (planned for the API hardening phase).
