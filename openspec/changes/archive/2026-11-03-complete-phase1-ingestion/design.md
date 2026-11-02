# Design

## Context

Current state, read from the code: `services/ocr_ingest.py` loops over pages still marked `scanned` in batches of 10, downloads each image, runs `OcrEngine.read` in `asyncio.to_thread` one page at a time, and commits per batch. The PDF spec already requires that a 1000-page PDF is processed with flat memory, but no test in `tests/` has that many pages; the earlier "1000 pages in about 4 seconds" was a manual run, and the memory evidence was inconclusive. `add-spreadsheet-parsing` is proposed and edits `run_pipeline` and the task message table, so it is applied first. See `proposal.md` for motivation and `specs/` for requirements.

## Goals / Non-Goals

**Goals:**
- Faster OCR of large scans using the cores a worker already has, with the smallest possible code change.
- Measured, reproducible numbers for the 1000-page case, kept out of the default test run.
- Every Phase 1 checklist item either tested or explicitly closed.

**Non-Goals:**
- Distributing one document's batches over several workers, vision fallback, stage-history refactoring (see proposal).

## Decisions

**D1. Concurrency inside the OCR job, not extra Celery tasks.** `ocr_pages` reads each batch of up to 10 pages with `asyncio.gather` over `asyncio.to_thread(engine.read, ...)`, guarded by an `asyncio.Semaphore(OCR_CONCURRENCY)`. Tesseract runs as a separate process per call and OpenCV releases the GIL, so threads give real parallelism. Database writes stay sequential after each batch, so no session is shared between threads, commits stay one per batch, and the `scanned` marker keeps the job idempotent. Alternative: fan out one Celery task per page batch plus a "last batch completes the document" rule. More moving parts (completion race, partial failure, new task and tests) for a speedup the in-process version already gives per worker; it stays as the scaling option if Phase 6 numbers call for it. To avoid oversubscribing cores, the engine pins Tesseract to one thread per call (`OMP_THREAD_LIMIT=1`, set when the module loads, only if not already set) and OpenCV to one thread (`cv2.setNumThreads(1)`): parallelism then comes from the pages, not from each library fighting for the same cores.

**D2. Setting.** `ocr_concurrency` (`OCR_CONCURRENCY`, int, default 4, `ge=1`) in `core/config.py`, naming its environment variable like the others, documented in `.env.example`.

**D3. Large-document evidence is an opt-in slow test.** A `slow` marker is registered in `pyproject.toml` and deselected by default (`-m "not slow"` in `addopts`); `make bench` runs `pytest -m slow -s`. The test (a) ingests a generated 100-page and then a 1000-page text PDF through `ingest_pdf` with `FakeStorage` and a real database, records `ru_maxrss` after each and fails if the 1000-page run raised peak memory by more than 100 MB over the 100-page run (a bound tuned after the first measured run and recorded), and prints seconds per 100 pages; (b) runs OCR over a generated 40-page scanned document with `OCR_CONCURRENCY` 1 and 4, asserts identical results and prints both times and the speedup (informational: it depends on the machine's cores and is not asserted). The measured numbers, machine and date go into `docs/performance.md`, which the evaluation phase extends. Alternative: a standalone script outside pytest. The test reuses the database fixtures and fails loudly instead of rotting.

**D4. Fixture audit as a table plus gap tests.** `docs/testing.md` holds a table mapping every Phase 1 fixture item and routing case to the test that covers it (file and test name). Items with no test get one: wrong extension (a PNG named `.pdf` is routed as an image by content, a PDF named `.jpg` as a PDF) and routing of each `source_type` to its ingest function in `run_pipeline`. Spreadsheet rows of the table point to the tests from `add-spreadsheet-parsing`. Documentation and tests only, no production code.

**D5. Order.** Apply `add-spreadsheet-parsing` first (it edits `run_pipeline` and the task message table), then this change; its phase-gate group checks all of Phase 1 including spreadsheets.

## Risks / Trade-offs

- [Several documents on several worker processes, each running 4 page threads, oversubscribe the machine] -> Concurrency is a setting; `docs/performance.md` states that total parallelism is worker processes times `OCR_CONCURRENCY` and how to size `--concurrency`; the thread pinning keeps each page to one core.
- [Memory of 4 decoded pages at once on very large scans] -> Pages are capped at 5000 px per side by the readers, so 4 pages stay in the low hundreds of MB; `make bench` reports the figure.
- [Memory bound of 100 MB is a guess before the first measurement] -> Task 3.3 runs it, records the real figure and sets the bound with headroom.
- [Slow tests excluded by default can rot] -> `make bench` is part of the phase gate, and CI keeps running the default set.

## Migration Plan

No schema change, no new dependency. Optionally set `OCR_CONCURRENCY`. Rollback: revert the code.
