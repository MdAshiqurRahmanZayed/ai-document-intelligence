# Proposal

## Why

Phase 1 can read digital PDFs, but image files (JPG, PNG, TIFF) and scanned PDF pages still produce no text: the PDF change leaves scanned pages marked `scanned` and waiting. Without OCR, a large share of real invoices and receipts cannot reach the extraction phase.

## What Changes

- Accept image documents (JPG, PNG, single- and multi-page TIFF): each frame becomes one page record with a stored PNG, using the same `scanned` marker as scanned PDF pages.
- Add OCR for every page marked `scanned`, whether it came from an image or a PDF: clean up the picture (grayscale, deskew, denoise, contrast, threshold, despeckle), read it with Tesseract, and save the text, the method `ocr` and a page confidence.
- Run OCR as its own background job on the existing `ocr` queue, so a slow scan-heavy document does not hold the ingest job. The document stays `PROCESSING` until its pages are read, then becomes `COMPLETED`.
- Fail unreadable images with a clear code (`image_corrupt`) and OCR failures with `ocr_failed`.
- Clear a page's stale confidence whenever its page record is re-saved by the PDF reader.
- Install Tesseract and OpenCV in the backend images and in CI; document the new error codes and stage in the API and schema docs.

Out of scope:
- Gemini vision fallback for low-confidence pages (needs the LLM client from Phase 2; `vision` stays a reserved method value and the confidence is stored so the rule can be added later).
- Table detection, handwriting, and languages other than English.
- Parallel OCR of the pages of one document (sequential first; measured in the evaluation phase).
- Spreadsheets, LLM extraction, validation, search and the review UI.

## Capabilities

### New Capabilities
- `image-ingestion`: image documents become page records with stored page images; unreadable images fail with a clear code.
- `page-ocr`: pages marked `scanned` are cleaned up, read with OCR, and saved with text, method and confidence; runs as its own job.

### Modified Capabilities
- `document-status`: a document is `COMPLETED` only once its pages have text; the ingest job hands pages that need OCR to a follow-up job and leaves the document `PROCESSING` until it finishes.

## Impact

- Code: new `pipeline/image.py`, `pipeline/preprocess.py`, `pipeline/ocr.py`; new `services/image_ingest.py`, `services/ocr_ingest.py`, shared page saving; `workers/tasks.py` (dispatch, new OCR task, new error codes).
- Dependencies: `pytesseract`, `opencv-python-headless`, `numpy`; system package `tesseract-ocr` (English data) in the backend test and runtime images and in the CI job.
- Data: no schema change; `pages.method` now also takes `ocr` in practice, `ocr_confidence` is filled (0 to 1), `processing_events.stage` gains `ocr`.
- Docs: `docs/api.md` (error codes, stages, `page_count` for images), `docs/database-schema.md`.
