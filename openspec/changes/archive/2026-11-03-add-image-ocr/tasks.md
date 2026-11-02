# Tasks

## 1. Dependencies and tooling

- [x] 1.1 Add `pytesseract`, `opencv-python-headless` and `numpy` to `backend/pyproject.toml` (mypy overrides for untyped modules), refresh `uv.lock`, install `tesseract-ocr` in the Dockerfile test and runtime stages and in the CI backend job, and verify by running `tesseract --version` and `import cv2, pytesseract` inside the rebuilt backend image
- [x] 1.2 Create `tests/image_samples.py` that draws known text with Pillow and builds: a clean page, a rotated (skewed) page, a noisy page, a blank page, a multi-frame TIFF, a JPG with EXIF rotation, an oversized image and a truncated JPG; verify each one decodes (or fails) as intended with a small test

## 2. Reading images

- [x] 2.1 Create `app/pipeline/image.py` (`ImageError` with code, `ImageReader` with `page_count()` and a lazy `pages()` generator yielding frame number and PNG bytes; EXIF orientation, RGB conversion, scale down to `MAX_IMAGE_SIDE` never up, decode and decompression-bomb errors mapped to `image_corrupt`) with comments for non-obvious choices, and unit tests for: JPG, PNG, three-frame TIFF, EXIF-rotated photo comes out upright, oversized image scaled to the cap, small image not enlarged, truncated image and unrecognised data raise `image_corrupt`, frames are produced lazily; verify they pass

## 3. Saving pages and ingesting images

- [x] 3.1 Move the batch upsert from `services/pdf_ingest.py` into `services/pages.py`, set `ocr_confidence` to NULL in the upsert, and keep `pdf_ingest` using it; verify the existing PDF integration tests still pass and add a test that re-saving a previously OCR'd page clears its text and confidence
- [x] 3.2 Create `app/services/image_ingest.py` (download to a temp file, set `page_count`, store each frame image before its row, batched upsert as `scanned`, no FastAPI imports) with DB tests using `FakeStorage` for: single image, three-frame TIFF, re-run leaves one row per page, upload failure leaves no row pointing at a missing image; verify they pass

## 4. OCR engine

- [x] 4.1 Create `app/pipeline/preprocess.py` (`Preprocessor` with grayscale, deskew limited to 0.5 to 15 degrees, denoise, CLAHE, adaptive threshold and despeckle as separate commented steps) and unit tests for: output is single-channel, a rotated sample is straightened to within one degree, an already-straight sample is left alone, a noisy sample keeps its text readable; verify they pass
- [x] 4.2 Create `app/pipeline/ocr.py` (`OcrEngine.read(png_bytes)` returning text and confidence 0 to 1 from the mean of word confidences, -1 entries ignored, empty result for no words, 120 second timeout) and tests: stubbed `image_to_data` for the confidence arithmetic and blank page, plus real Tesseract on the clean, skewed and noisy samples asserting the known words and confidence above 0.8 for the clean one; verify they pass

## 5. OCR job and task wiring

- [x] 5.1 Create `app/services/ocr_ingest.py` (`ocr_pages(session, storage, document)`: select pages with method `scanned` in order, batches of 10, download each image, run the engine in `asyncio.to_thread`, update text, method `ocr` and confidence, one commit per batch) with DB tests for: scanned pages become `ocr` with text and confidence, native pages untouched, re-run reads only remaining `scanned` pages, blank page saved empty without failing; verify they pass
- [x] 5.2 Wire the tasks in `workers/tasks.py`: `run_pipeline` dispatches `image` documents to `image_ingest` and returns whether OCR is pending; the ingest job queues `ocr_document` on the `ocr` queue and leaves the document `PROCESSING` when pages need OCR; `ImageError` shares the non-retried branch with `PdfError` (message table gains `image_corrupt`); add the `ocr_document` task with the same retry policy, stage `ocr` events, `COMPLETED` when done and `ocr_failed` via `on_failure`; update the existing task tests and add tests for: image end to end (`COMPLETED` after the OCR job, text saved), scanned PDF (ingest leaves `PROCESSING`, OCR job completes it), all-text PDF queues no OCR job, truncated image (`FAILED` `image_corrupt` after one attempt), OCR error then success, OCR retries exhausted (`ocr_failed`); verify `make test` passes

## 6. Docs

- [x] 6.1 Update `docs/api.md` (error codes `image_corrupt` and `ocr_failed`, stage `ocr` in the history example, `page_count` for images, status flow while OCR is pending) and `docs/database-schema.md` (`method` `ocr`, `ocr_confidence` scale and when it is cleared, `stage` values, scanned-page lifecycle), and verify the documented values match the code

## 7. Integration verification

- [ ] 7.1 Rebuild the stack (`make up`), upload a JPG of an invoice-like page, a multi-page TIFF and a mixed PDF with a scanned page, and verify page rows, method `ocr`, text, confidence, `PROCESSING` between the two jobs and `COMPLETED` at the end, and the `ocr` events in the history
- [ ] 7.2 Upload a truncated JPG and verify `FAILED` with `image_corrupt` and a single attempt in the history
- [ ] 7.3 Run `make lint`, `make test` (earlier tests included) and `openspec validate add-image-ocr --strict`, and verify all pass

## Workflow follow-up

- Update the Phase 1 checkboxes and daily log in `~/Desktop/personal-project/ai-document-intelligence.md`.
- Archive with `/opsx:archive`, then commit in atomic commits on `feat/ocr-add-image-ocr`.
- Push only when asked; open the PR into `main`.
