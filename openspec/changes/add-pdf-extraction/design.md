# Design

## Context

The ingest task (`app/workers/tasks.py`) already moves a document `QUEUED -> PROCESSING -> COMPLETED`, retries failures, and calls a placeholder `run_pipeline(document)`. The `pages` table exists and is empty. Storage is S3 (SeaweedFS) behind a `Storage` protocol with `put`, `delete`, `presigned_url`; files live at `raw/<document_id>/original.<ext>`. Types are already detected at upload, so `documents.source_type` says whether a document is a PDF. See `proposal.md` for motivation and `specs/pdf-text-extraction` for requirements.

## Goals / Non-Goals

**Goals:**
- Reliable per-page text for PDFs up to about 1000 pages with flat memory use.
- A clear, queryable marker for pages that need OCR, with their images ready.
- Failures that tell the user what is wrong and do not waste retries.

**Non-Goals:**
- OCR, tables, page-reading API, non-PDF files, parallel page processing (see D4).

## Decisions

**D1. `pypdfium2` for both text and rendering.** One library reads text (`get_textpage`) and renders pages (`render`), has a permissive license (BSD/Apache) and ships PDFium inside its wheels, so the slim Docker images need no system packages. Alternatives: PyMuPDF (fastest, but AGPL-licensed, which complicates sharing the code), pdfplumber/pdfminer (pure Python, 10x or more slower and heavier on memory for big files; its strength, tables, is out of scope here).

**D2. Layering.** `app/pipeline/pdf.py` is pure: path in, page results out; no database, storage or web imports. `app/services/pdf_ingest.py` does the I/O (download, upload images, save rows). The task's `run_pipeline` only dispatches on `source_type`. This keeps the PDF logic testable with plain files and reusable by the OCR change.

**D3. One page at a time, from a temp file.** The worker streams the stored object into a temporary file on disk and opens it by path; PDFium reads pages on demand. Each page, text page and bitmap is closed before the next. Memory stays flat regardless of page count; the whole PDF is never in RAM. Alternative: load the bytes into memory (up to 100 MB per worker plus copies).

**D4. Sequential per document, not a parallel fan-out.** The earlier plan suggested a Celery chord with one task per page batch. Native text extraction is fast (PDFium reads a text page in milliseconds), the slow part is OCR, which the next change will parallelize. A chord adds shared state, a join step and more failure modes. Sequential extraction still gets resilience from batching and idempotency (D6). If measurement in the evaluation phase shows a real need, fan-out can be added without changing the data model.

**D5. Scanned means fewer than 20 non-whitespace characters.** A single named constant with a comment. Pages with a hidden OCR text layer count as native (they already have text). The threshold is tuned later from evaluation results if needed.

**D6. Batched, idempotent saves.** Rows are written in batches of 25 pages with `INSERT ... ON CONFLICT (document_id, page_no) DO UPDATE` and one commit per batch. Progress survives a crash, and a retry or later reprocess updates rows in place instead of failing on the unique constraint. `page_count` is set before the first batch so progress can be shown. For each batch the images are uploaded first, then the rows are saved, so a row never points at a missing object.

**D7. Render only scanned pages, at 300 DPI, capped.** Scale is `300 / 72`; if the longest side would exceed 5000 pixels the scale is reduced to fit, which prevents a huge page from exhausting memory (an A4 page at 300 DPI is about 3500 pixels, so normal pages are unaffected). Images are PNG (lossless, best for OCR) and stored at `pages/<document_id>/<page_no>.png`. Text pages are not rendered: it would cost 1 to 3 GB per 1000 pages for nothing, since the viewer can display the original PDF directly. Alternative: render everything, as the original plan said.

**D8. `method` and the scanned convention, no migration.** `pages.method` takes `native`, `scanned` (waiting for OCR), `ocr` and `vision`. A scanned page has `text` NULL and `image_key` set; the OCR change fills `text`, sets `method = "ocr"`, and keeps the image. The `String(20)` column already fits.

**D9. Error classification.** `pipeline/pdf.py` raises `PdfError` carrying a code: a password failure from PDFium becomes `pdf_encrypted`, any other load failure `pdf_corrupt`, zero pages `pdf_empty`. The task catches `PdfError`, marks the document `FAILED` with that code, writes a `failed` event and returns without raising, so Celery does not retry a PDF that will never open. Other exceptions (network, database, storage) still raise and are retried as before.

**D10. NUL characters.** PostgreSQL text cannot hold `\x00`, and PDFs sometimes produce it. It is stripped from page text before saving.

**D11. `run_pipeline` signature.** It becomes `run_pipeline(session, storage, document)`. The task builds the storage client once per run with the existing `build_s3_storage`. Existing task tests that replace the pipeline are updated to the new signature.

**D12. Storage `download`.** `Storage` gains `download(key, fileobj)` backed by `download_fileobj`, using the same `CHUNK_SIZE` transfer settings. The in-memory fake implements it.

**D13. Test PDFs are generated, not committed.** `reportlab` (dev only) builds text PDFs, an image-only PDF (a page with a drawn image and no text), a mixed PDF, an encrypted PDF, and a many-page PDF; truncating bytes makes a corrupt one and a hand-written minimal file gives zero pages. This keeps the repository free of binary fixtures and lets tests control page counts.

## Risks / Trade-offs

- [PDFium's error messages and codes may differ between versions] → Classification uses PDFium's error code where available; tests use real encrypted and truncated files, so a version change shows up as a failing test.
- [A very long job can outlive Redis's visibility timeout (1 hour by default) and be delivered again, because tasks acknowledge late] → Re-runs are harmless (idempotent upserts); a 1000-page PDF should finish well within the hour. Revisit if the evaluation shows otherwise.
- [A hidden or low-quality text layer makes a poor page count as native] → Out of reach for a character-count rule; surfaced by evaluation, and `vision` fallback in Phase 1's OCR change covers poor pages.
- [Scanned pages cost disk (1 to 3 MB each)] → Only scanned pages are rendered, and images can be deleted and regenerated later.
- [PDFium is native code processing untrusted files] → It runs in the unprivileged worker container; corrupt input ends as `pdf_corrupt`, not a crash of the API.
- [Sequential processing is slower than a fan-out for huge scanned PDFs] → Acceptable until measured; the data model already supports splitting the work later.
- [Documents already processed before this change have no pages] → Re-running them needs the reprocess endpoint (Phase 4); until then a one-off `ingest_document.delay(<id>)` from a shell works because the job is idempotent.

## Migration Plan

No schema change. Deploy by rebuilding and restarting the API and worker (`make up`). Rollback: revert the code; extra rows in `pages` and objects under `pages/` are harmless.
