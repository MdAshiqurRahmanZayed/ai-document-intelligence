# Tasks

## 1. Dependencies and storage download

- [x] 1.1 Add `pypdfium2` and `pillow` (runtime) and `reportlab` (dev) to `backend/pyproject.toml`, refresh `uv.lock`, and verify the backend image builds and imports `pypdfium2` and renders a page inside the container
- [x] 1.2 Add `download(key, fileobj)` to the `Storage` protocol and `S3Storage` (using the shared `CHUNK_SIZE` transfer config) and to `FakeStorage`, with a unit test that it calls `download_fileobj` with the right bucket, key and config; verify it passes

## 2. PDF reading

- [x] 2.1 Create `tests/pdf_samples.py` that generates test PDFs with reportlab (text, image-only, mixed, password-protected, many-page) plus a truncated and a zero-page variant, and verify each opens or fails as intended with `pypdfium2`
- [x] 2.2 Create `app/pipeline/pdf.py` (`PdfError` with code, `page_count`, and a lazy `extract_pages` generator yielding page number, text and, for scanned pages only, PNG bytes; NUL stripping, scanned threshold, 300 DPI render with the pixel cap, error classification) with comments for the non-obvious constants, and unit tests for: text pages, scanned page, mixed PDF, NUL removal, oversized page scaled down, encrypted, corrupt, zero pages, and that pages are produced lazily; verify they pass

## 3. Saving pages

- [x] 3.1 Create `app/services/pdf_ingest.py` that downloads the stored PDF to a temp file, sets `page_count`, uploads scanned-page images then upserts page rows in batches of 25 with one commit per batch, with no FastAPI imports; add DB tests with `FakeStorage` for: text PDF rows and count, mixed PDF stores images only for scanned pages and references them, re-run leaves exactly one row per page, image upload failure leaves no row pointing at a missing image, and the batch size is respected (patched small batch); verify they pass

## 4. Task wiring

- [x] 4.1 Change `run_pipeline` to `run_pipeline(session, storage, document)`, dispatch PDFs to `pdf_ingest`, build the storage client in the task, and handle `PdfError` by marking the document `FAILED` with its code, writing a `failed` event and returning without retry; update the existing task tests to the new signature and add tests for: PDF end to end (`COMPLETED`, pages saved), corrupt PDF (`FAILED` `pdf_corrupt` after exactly one attempt), encrypted PDF (`pdf_encrypted`), zero-page PDF (`pdf_empty`), and a CSV document (`COMPLETED`, no pages); verify `make test` passes

## 5. Docs

- [x] 5.1 Update `docs/api.md` (error codes `pdf_corrupt`, `pdf_encrypted`, `pdf_empty`; `page_count` now filled) and `docs/database-schema.md` (`pages.method` values and the scanned convention, `pages/` prefix in the bucket), and verify the documented values match the code

## 6. Integration verification

- [x] 6.1 Rebuild the stack (`make up`), upload a digital PDF and an image-only PDF, and verify `page_count`, page rows with method `native` and `scanned`, and a PNG only for the scanned page in the bucket
- [ ] 6.2 Generate a 1000-page PDF, upload it, and verify it reaches `COMPLETED` with 1000 page rows, recording total time and the worker's peak memory (`docker stats`) to confirm memory stays flat (deferred by the user: 1000 pages completed in about 4 s, memory evidence not conclusive)
- [x] 6.3 Upload a truncated PDF and a password-protected PDF and verify `FAILED` with `pdf_corrupt` and `pdf_encrypted`, each with a single attempt in the history
- [x] 6.4 Run `make lint`, `make test` (earlier tests included) and `openspec validate add-pdf-extraction --strict`, and verify all pass

## Workflow follow-up

- Update the Phase 1 checkboxes and daily log in `~/Desktop/personal-project/ai-document-intelligence.md`.
- Archive with `/opsx:archive`, then commit in atomic commits on `feat/pdf-add-pdf-extraction`.
- Push only when asked; open the PR into `main`.
