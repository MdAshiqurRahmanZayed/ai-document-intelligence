# Design

## Context

The ingest task (`workers/tasks.py`) dispatches on `documents.source_type`. For PDFs, `services/pdf_ingest.py` saves one `pages` row per page; pages with almost no text get method `scanned`, no text and a stored 300 DPI PNG (`image_key`). Image documents (`source_type = "image"`) are accepted at upload but the ingest job does nothing for them yet. The `ocr` Celery queue already exists and the worker already listens to it. `pages.ocr_confidence` exists and is unused. See `proposal.md` for motivation and `specs/` for requirements.

## Goals / Non-Goals

**Goals:**
- One OCR path for scanned PDF pages and for image frames, because both are "a stored page image with no text".
- A slow OCR run never blocks the ingest queue and survives a crash without redoing finished pages.
- Preprocessing that is simple, deterministic and testable without a real scan.

**Non-Goals:**
- Vision (Gemini) fallback, tables, handwriting, extra languages, per-page parallelism, tuning the clean-up from evaluation data (see proposal).

## Decisions

**D1. Tesseract through `pytesseract`, OpenCV (headless) for clean-up.** Tesseract is the plan's engine, needs no API key and runs offline in tests. `pytesseract` calls the `tesseract` binary, which is installed as the `tesseract-ocr` system package (English data only) in the backend test and runtime images and in CI. `opencv-python-headless` (no GUI libraries) plus `numpy` do the clean-up. Alternatives: EasyOCR/PaddleOCR (GPU-oriented, large model downloads), cloud OCR (cost, key, network in tests).

**D2. Layering mirrors the PDF change.** `pipeline/image.py` (`ImageReader` class: path in, one PNG per frame out), `pipeline/preprocess.py` (`Preprocessor`: grayscale picture in, cleaned picture out) and `pipeline/ocr.py` (`OcrEngine`: PNG bytes in, text and confidence out) are pure: no database, storage or web imports. `services/image_ingest.py` and `services/ocr_ingest.py` do the I/O. Page-row saving, already in `pdf_ingest.py`, moves to a shared `services/pages.py` so PDFs and images use one upsert.

**D3. OCR is a separate task on the `ocr` queue.** After extraction, the ingest job counts pages with method `scanned`. If there are none the document becomes `COMPLETED` as before. Otherwise it commits, queues `ocr_document(document_id)` on the `ocr` queue, writes its own `succeeded` event for stage `ingest` and leaves the document `PROCESSING`. The OCR task reads pages still marked `scanned` in page order, in batches of 10, and saves each batch with one commit; when none are left it sets `COMPLETED`. Alternative: OCR inside the ingest job. Rejected because Tesseract at 1 to 3 seconds per page means a 1000-page scan could run for most of an hour, which risks Redis's redelivery timeout (the ingest job acks late) and blocks fast text extraction behind it. Queueing is the last step of the ingest job, so if it fails the job retries, and the whole ingest is idempotent.

**D4. Idempotency comes from the `scanned` marker.** The OCR job selects `WHERE method = 'scanned'`, so a crash or redelivery resumes with the remaining pages and finished pages are never touched. Re-ingesting a document upserts its pages back to `scanned` with `text` and now also `ocr_confidence` set to NULL (the stale-confidence issue noted in the PDF change review), so a reprocess starts from a clean state.

**D5. One page image format for both sources.** `ImageReader` opens the file with Pillow, applies EXIF orientation (`ImageOps.exif_transpose`, so phone photos are upright), converts each frame (`ImageSequence`) to RGB, scales the longest side down to `MAX_IMAGE_SIDE` (5000, reused from the PDF reader; never up) and encodes PNG. One frame at a time is held in memory, so a long TIFF stays flat. Frame pages are saved with method `scanned` at `pages/<document_id>/<page_no>.png`, the same layout the PDF change uses, so OCR does not care where a page came from.

**D6. Decode failures are `image_corrupt`, not retried.** Pillow raising on a truncated or damaged file, `Image.DecompressionBombError` for absurd pixel counts, and an unrecognised format are all caught in `ImageReader` and raised as `ImageError("image_corrupt")`. The task handles it like `PdfError`: `FAILED` with the code, a failed event, no retry. Pillow's truncated-image tolerance stays off (its default), so a cut-off file fails instead of yielding a half-grey page.

**D7. Clean-up pipeline: grayscale, deskew, denoise, contrast, threshold, despeckle.**
- Grayscale: the page is decoded straight to one channel (`cv2.imdecode` with `IMREAD_GRAYSCALE`).
- Deskew: the tilt is searched on a shrunken copy: the dark (text) pixels are rotated through -15 to +15 degrees in 0.5 degree steps and the angle whose row sums vary most (text lines against gaps) wins; ties prefer the smaller turn. A correction is applied only when it is 0.5 degree or more (up to the 15 degree search limit): larger angles are more likely a wrong estimate than a real tilt, and less than 0.5 degree is noise.
- Denoise: median blur (3x3, removes speckle) followed by a light Gaussian blur (3x3, smooths the grain the median leaves). Chosen over `fastNlMeansDenoising`, which takes seconds on a 5000 px page.
- Contrast: CLAHE (local contrast), which helps faded thermal receipts.
- Threshold: Gaussian adaptive threshold (51 px neighbourhood) where a pixel must be 25 levels darker than its surroundings to count as ink. Lower offsets turn sensor noise into dense black dots.
- Despeckle: black connected blobs under 12 pixels are erased. Found with the noisy test sample: a few hundred 2 to 5 pixel specks left after thresholding made Tesseract's layout step find no text at all (empty result), although it read the same page unprocessed.
Each step is a small method on `Preprocessor`; constants are named and commented. The cleaned picture is passed to Tesseract in memory only; the stored PNG is untouched, so later stages (vision, the viewer) see the original. The strength of each step is a starting point; the evaluation phase measures and tunes it.

**D8. Confidence from `image_to_data`.** `pytesseract.image_to_data(..., output_type=DICT)` gives text and a 0 to 100 confidence per word, with -1 for non-words. The page text is built from the same data: words grouped into lines by Tesseract's block, paragraph and line numbers, lines joined with newlines; the page confidence is the mean of the confidences that are 0 or more, divided by 100 so it is a 0 to 1 number, matching the field confidences later phases will use. No recognised words gives empty text and NULL confidence, and a blank page is a normal result, not a failure. Page segmentation uses Tesseract's default automatic mode; a per-call timeout (120 seconds) turns a hung call into an exception that the retry policy handles.

**D9. Task wiring and error codes.** `run_pipeline` returns whether OCR is pending. `_run` keeps its structure: `PdfError` and `ImageError` share one branch (both carry a code and are not retried; messages come from one table), other exceptions retry up to 3 times and end as `ingest_failed`. `ocr_document` is a second task with the same retry policy and its own `on_failure` that sets `ocr_failed`. Events use stage `ocr` with the same started/succeeded/failed attempt rows.

**D10. Vision fallback is deferred.** It needs the LangChain/Gemini client, which belongs to Phase 2. This change stores the confidence and keeps `vision` as a reserved `method`; the fallback becomes a small addition to the OCR job (pages below a threshold are re-read) once the client exists.

**D11. Test images are generated, not committed.** Pillow draws known text in a large font on a white canvas (`tests/image_samples.py`), with helpers to rotate it (skew), add noise, build a multi-frame TIFF, tilt via EXIF orientation, and truncate bytes. The OCR tests run the real Tesseract on those images and assert the known words (with tolerance on confidence). Unit tests that only need the numbers (mean of word confidences, -1 filtering, blank page) feed a stubbed `image_to_data`.

## Risks / Trade-offs

- [Tesseract is missing or a different version in CI or the image] -> Install `tesseract-ocr` explicitly in the Dockerfile stages and the CI job; an OCR test that fails to find the binary fails loudly instead of skipping.
- [Real-image accuracy depends on the clean-up steps; a bad threshold can hurt clean pages] -> Steps are separate and covered by tests on skewed and noisy samples; evaluation (Phase 6) measures accuracy on degraded images and the constants are tuned there.
- [Deskew guesses wrong on a page with large non-text areas or rotated 90 degrees] -> The 15 degree limit stops large wrong rotations; pages sideways by 90 degrees are not corrected in this change (orientation detection is deferred).
- [`opencv-python-headless` and numpy add roughly 100 MB to the image] -> Accepted; headless avoids the GUI system libraries.
- [Sequential OCR of a huge scan is slow] -> Runs on its own queue and resumes by batch; per-page parallelism can be added later without changing the data model.
- [Document status now spans two jobs, so a lost OCR job leaves a document `PROCESSING`] -> The OCR job is queued as the last step of ingest and acknowledged late; a stuck-document sweep belongs with the reprocess endpoint in Phase 4.
- [Tesseract English only] -> Non-English invoices read poorly; a language setting can be added when evaluation shows the need.

## Migration Plan

No schema change. Rebuild the backend images (`make up`) so Tesseract and OpenCV are installed, and add `tesseract-ocr` to the CI job. Documents processed before this change that have `scanned` pages can be OCR'd by queueing `ocr_document.delay(<id>)` from a shell; re-uploading an image that previously did nothing needs the reprocess endpoint (Phase 4) or a manual `ingest_document.delay(<id>)`. Rollback: revert the code; extra `ocr` pages and events are harmless.
