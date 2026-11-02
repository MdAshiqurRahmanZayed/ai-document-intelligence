# API reference

Base URL (local): `http://localhost:8000`. Interactive docs (generated, always current): `/docs`.

Keep this file in sync with the code whenever an endpoint, field or error reason changes.

## Contents

- [Health](#health)
- [Upload documents](#upload-documents)
- [Get a document](#get-a-document)
- [Get the extraction result](#get-the-extraction-result)
- [Cross-verify two documents](#cross-verify-two-documents)
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

`events` is the processing history, oldest first. `stage` is `ingest` (reading the file and saving its pages) `ocr` (reading the text of scanned pages and images; only present when a document has such pages) or `extract` (reading the invoices and validating them; only present when extraction is enabled). A failed attempt adds a `failed` event; its retry then adds a `started` event with the next `attempt` number.

| Response | When |
|---|---|
| `404` | No document with that id |
| `422` | `document_id` is not a valid UUID |

## Get the extraction result

`GET /api/v1/documents/{document_id}/result`: the invoices read from a document, with confidence, source quotes and validation findings. Extraction runs only when a Google API key is configured; without one the invoice list stays empty.

```bash
curl localhost:8000/api/v1/documents/3f2a…/result
```

**`200`**

```json
{
  "document_id": "3f2a…",
  "status": "NEEDS_REVIEW",
  "invoices": [
    {
      "extraction_id": "9c1b…",
      "invoice_index": 0,
      "version": 1,
      "data": {
        "invoice_number": "INV-1042",
        "invoice_date": "2026-01-05",
        "supplier_name": "Acme Ltd",
        "customer_name": "Globex",
        "subtotal": "100.00",
        "tax": "20.00",
        "total": "130.00",
        "currency": "EUR",
        "line_items": [
          { "description": "Widget", "quantity": "2", "unit_price": "50.00", "amount": "100.00" }
        ]
      },
      "field_confidence": { "invoice_number": 0.95, "total": 0.9 },
      "grounding": { "invoice_number": "Invoice No: INV-1042" },
      "model": "gemini-2.5-flash",
      "prompt_version": "v1",
      "validation_errors": [
        { "code": "total_mismatch", "field": "total", "severity": "error",
          "message": "subtotal 100.00 plus tax 20.00 is 120.00, not 130.00", "related_document_id": null }
      ]
    }
  ],
  "document_errors": []
}
```

- `data` holds the normalized values: dates are ISO 8601, amounts are decimal **strings** (never floats), `currency` is an ISO 4217 code. A value the document does not state is `null`; a value that could not be found in the document text is dropped (`null`) with an `ungrounded_field` warning.
- `field_confidence` (0 to 1) and `grounding` (the quote each value came from) only list fields that have a value.
- A document can contain several invoices: one entry each, in order of `invoice_index`. Only the current version of each invoice is returned.
- `document_errors` holds findings about the whole document (`no_invoice_found`).

| Response | When |
|---|---|
| `200` with `"invoices": []` | Nothing was extracted (yet, or extraction is disabled) |
| `404` | No document with that id |
| `422` | `document_id` is not a valid UUID |

## Cross-verify two documents

`POST /api/v1/cross-verify`: compare the invoices of two documents, for example a PDF against an Excel export, or two PDFs. Both documents must have been extracted.

```bash
curl -X POST localhost:8000/api/v1/cross-verify -H 'Content-Type: application/json' \
  -d '{"left_document_id": "3f2a…", "right_document_id": "8d4e…"}'
```

**`200`**

```json
{
  "checks": [
    {
      "status": "mismatch",
      "match_key": "inv7",
      "left":  { "extraction_id": "9c1b…", "data": { "invoice_number": "INV-7", "total": "120.00" } },
      "right": { "extraction_id": "5a77…", "data": { "invoice_number": "INV-7", "total": "125.00" } },
      "diffs": [ { "field": "total", "left": "120.00", "right": "125.00" } ]
    }
  ]
}
```

- Each invoice of the left document is matched to at most one invoice of the right document: first by invoice number (ignoring case, spaces and punctuation: `INV-007` equals `inv 007`), otherwise by the same supplier name and total. `match_key` says how.
- `status` is `match` (no difference), `mismatch` (see `diffs`) or `unmatched` (an invoice with no partner: `left` or `right` is `null`).
- Compared fields: `invoice_date`, `supplier_name`, `customer_name`, `subtotal`, `tax`, `total`, `currency`, `line_item_count` and `line_item_sum`. Amounts that differ by 0.01 or less are equal; names are compared ignoring case, punctuation and company forms (Ltd, Inc, GmbH).
- The result is stored. Comparing the same two documents again replaces it.

| Response | When |
|---|---|
| `404` | Either document does not exist |
| `409` | Either document has no extracted invoices. Body: `{"detail": {"reason": "not_extracted", "document_id": "…"}}` |
| `422` | Both ids are the same document, or an id is not a valid UUID |

## Reference

### Document statuses

| Status | Meaning |
|---|---|
| `UPLOADED` | Stored and recorded, not yet handed to the queue (brief) |
| `QUEUED` | Waiting for a worker |
| `PROCESSING` | A worker is running a job. Stays `PROCESSING` between the ingest, OCR and extraction jobs |
| `COMPLETED` | All jobs finished and validation found nothing that needs a person (after the OCR job for scanned pages, after the extraction job when extraction is enabled) |
| `NEEDS_REVIEW` | Extraction finished but a person should look: a validation error, a low-confidence field, a duplicate invoice, or no invoice found. See the findings in `/result` |
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
| `extraction_failed` | The extraction job failed on every attempt (the model could not be reached or answered unusably, after trying the fallback model); `error_message` holds the exception type |

`page_count` is filled once the file has been opened, so it is already set while the pages are still being read: one per PDF page, one per image frame (a multi-frame TIFF has several), and for a spreadsheet the number of text pages (each sheet with data gives one page per 100 data rows). A spreadsheet document goes straight to `COMPLETED` after the ingest job: it never has an `ocr` stage.

### Validation findings

Each finding has a `code`, the `field` it concerns (when one), a `severity` and a message. `error` findings (and any `low_confidence` warning) send the document to `NEEDS_REVIEW`; other warnings do not.

| Code | Severity | Meaning |
|---|---|---|
| `missing_field` | error | invoice number, date, supplier or total is missing |
| `negative_amount` | error | a subtotal, tax, total, quantity, unit price or line amount is below zero |
| `implausible_amount` | error | an amount above 1 000 000 000 000 |
| `line_items_sum_mismatch` | error | line amounts do not add up to the subtotal (tolerance: the larger of 0.02 and 0.5 %) |
| `total_mismatch` | error | subtotal plus tax is not the total (same tolerance) |
| `future_date` | error | the invoice date is after today |
| `invalid_currency` | error | the currency is not an ISO 4217 code |
| `duplicate_invoice` | error | another document has an invoice with the same number and supplier; `related_document_id` names it |
| `no_invoice_found` | error | the document holds no invoice (a document-level finding) |
| `line_amount_mismatch` | warning | a line's amount differs from quantity times unit price by more than 0.02 |
| `implausible_tax_rate` | warning | tax is below 0 or above 30 % of the subtotal |
| `old_date` | warning | the invoice date is before 2000 |
| `missing_currency` | warning | no currency was found |
| `low_confidence` | warning (routes to review) | a field's confidence is below `LOW_CONFIDENCE_THRESHOLD` (default 0.5) |
| `possible_duplicate` | warning | another document has the same supplier, total and date with a different number; `related_document_id` names it |
| `ungrounded_field` | warning | a value was not found in the document text and was dropped |
| `unparseable_value` | warning | a value was present but could not be read as a date or amount and was dropped |

### Limits

- `MAX_UPLOAD_MB` (env, default 100): per file.
- Files are read in 8 MiB chunks, so memory use does not grow with file size.
- No limit yet on files per request, and no authentication or rate limiting (planned for the API hardening phase).
