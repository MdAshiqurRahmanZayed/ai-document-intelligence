# Proposal

## Why

Task 1 of the assignment asks for ingestion of PDF, image, Excel and CSV files, including documents of about 1000 pages, with high speed and tests for processing, OCR and failure scenarios. After `add-upload-and-storage`, `add-pdf-extraction` and `add-image-ocr`, and with `add-spreadsheet-parsing` proposed, two things the assignment asks for are still missing: OCR reads one page at a time, so a 1000-page scan is slow, and the 1000-page claim has no automated evidence. The Phase 1 test fixture list and the phase gate were also never checked off. This change closes exactly those, with the smallest code that does the job, so Phase 2 starts from a finished ingestion layer.

## What Changes

- **Concurrent OCR:** read the pages of one document concurrently, up to a configured limit (`OCR_CONCURRENCY`, default 4), instead of one after another. Results, batching and idempotency stay as they are.
- **Large-document evidence:** a slow, opt-in test (`make bench`) that ingests a 1000-page PDF and a scanned document, checks that memory does not grow with page count, and prints throughput; the measured numbers are recorded in `docs/performance.md`.
- **Test and fixture audit:** map every Phase 1 fixture (digital, scanned and mixed PDFs, JPG, PNG, multi-page TIFF, multi-sheet XLSX, XLS, `;` + Latin-1 CSV, corrupt PDF, truncated image, empty file, wrong extension) and the routing of each file type to a test, and add the missing ones.
- **Phase gate:** run lint, all tests and the manual demo of every file type, then tick Phase 1 in the master plan.

Out of scope (not required by the assignment, or later phases):
- The spreadsheet parser itself (`add-spreadsheet-parsing`, applied first).
- The Gemini vision fallback for low-confidence pages: OCR with pre-processing already meets the assignment's OCR requirement. It stays deferred until the evaluation phase measures OCR accuracy on degraded images.
- Refactoring how job stages write their history (the history exists and meets the assignment).
- Spreading the batches of one document over several workers (a scaling option if the evaluation phase calls for it).
- Any change to upload, API response shapes or the database schema.

## Capabilities

### New Capabilities

None.

### Modified Capabilities
- `page-ocr`: pages of one document are read concurrently up to a configured limit, with identical results whatever the limit.

## Impact

- Code: `services/ocr_ingest.py` (concurrent reads), `pipeline/ocr.py` (pin Tesseract and OpenCV to one thread each so concurrency does not oversubscribe cores), `core/config.py` (one setting).
- Tests/tooling: a `slow` test marker, a `make bench` target, the new slow tests, and gap tests from the audit.
- Config: `OCR_CONCURRENCY` documented in `.env.example`.
- Docs: new `docs/performance.md` and `docs/testing.md`; the master plan.
