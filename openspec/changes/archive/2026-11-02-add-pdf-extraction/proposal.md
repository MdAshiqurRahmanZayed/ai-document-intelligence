# Proposal

## Why

Uploaded PDFs are stored and queued, but the ingest job does nothing with them: no text, no page records, no page count. Every later phase (AI extraction, validation, search) starts from per-page text, and scanned pages need images ready for OCR. PDFs of around 1000 pages are explicitly in scope, so this must work page by page without holding a whole document in memory.

## What Changes

- **Text per page:** for each PDF page, the ingest job extracts the embedded text and saves one `pages` row (`page_no`, `text`, `method`), and sets `documents.page_count`.
- **Scanned page detection:** a page with (almost) no embedded text is recorded as `method = "scanned"` with no text. Such pages are rendered to a 300 DPI PNG saved in object storage under `pages/<document_id>/<page_no>.png`, ready for the OCR change. Pages that have text are not rendered.
- **Large PDFs:** pages are processed one at a time and saved in small batches; re-running a document updates its page rows instead of duplicating them, so a retry or crash resumes cleanly.
- **Unusable PDFs end clearly:** a corrupt, password-protected or zero-page PDF sets the document to `FAILED` with error code `pdf_corrupt`, `pdf_encrypted` or `pdf_empty`, without wasting retries.
- **Storage download:** the storage service gains a `download` operation so workers can read stored files.
- **Docs:** `docs/api.md` and `docs/database-schema.md` describe the new codes and the `pages` conventions.

**Out of scope:** OCR itself (`add-image-ocr`), table extraction, an API to read pages (Phase 4), images and spreadsheets, rendering pages that already have text (the Phase 5 viewer can render the PDF directly), password-protected PDFs with a supplied password, and splitting one PDF into several invoices (Phase 2).

## Capabilities

### New Capabilities
- `pdf-text-extraction`: turning a stored PDF into per-page text records, flagging scanned pages and preparing their images, and reporting unusable PDFs.

### Modified Capabilities
<!-- None: document-status keeps its requirements; the new failure codes are specified in pdf-text-extraction. -->

## Impact

- **New code:** `backend/app/pipeline/pdf.py` (PDF reading, no database or web imports), page-saving logic in `backend/app/services/`, tests with generated PDF fixtures.
- **Changed code:** `backend/app/workers/tasks.py` (the placeholder `run_pipeline` dispatches PDFs), `backend/app/services/storage.py` (`download`), `tests/fakes.py`.
- **New dependencies:** `pypdfium2` (PDF text and rendering; permissive license, bundles its own native library), `pillow` (PNG encoding); dev: `reportlab` (to generate test PDFs).
- **Database:** no schema change. `pages` already has the columns; `method` gains the value `scanned`.
- **Storage:** new `pages/` prefix in the existing bucket.
