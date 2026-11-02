# Tasks

Apply `add-spreadsheet-parsing` first; it edits `run_pipeline` and the task message table that group 3 also touches.

## 1. Concurrent OCR

- [x] 1.1 Add `ocr_concurrency` (`OCR_CONCURRENCY`, int, default 4, at least 1) to `core/config.py` with a config test for default, override and rejection of 0; document `OCR_CONCURRENCY` in `.env.example` (the assistant cannot read that file in this setup, so the user applies or approves the edit); verify `tests/unit/test_config.py` passes
- [x] 1.2 In `services/ocr_ingest.py` read each batch with `asyncio.gather` over `asyncio.to_thread(engine.read, ...)` behind an `asyncio.Semaphore(settings.ocr_concurrency)`, keeping sequential database writes and one commit per batch; in `pipeline/ocr.py` set `OMP_THREAD_LIMIT=1` (only if unset) and `cv2.setNumThreads(1)` with a comment; tests with a stub engine for: 12 pages with a limit of 4 never run more than 4 reads at once and all end `ocr`, a limit of 1 gives identical text and confidence, one failing read raises and leaves earlier committed batches saved; verify the existing `test_ocr_ingest.py` and the new tests pass

## 2. Large-document evidence

- [x] 2.1 Register the `slow` marker and `-m "not slow"` default in `pyproject.toml`, add a `make bench` target (`pytest -m slow -s` in the backend test container, same shape as `make test`), and create the slow test file with the 1000-page PDF test (ingest 100 then 1000 text pages with `FakeStorage` and the real database, record `ru_maxrss` after each, assert growth within the bound, print seconds per 100 pages); verify `make test` still skips it and `make bench` runs it
- [x] 2.2 Add the concurrent OCR benchmark to the slow tests (generated 40-page scanned document read with `OCR_CONCURRENCY` 1 then 4, assert identical results, print both times and the speedup); verify with `make bench`
- [x] 2.3 Run `make bench` on the target machine, set the memory bound from the measured figure with headroom, and create `docs/performance.md` with the measured numbers, machine, date, how to rerun, and a note that total parallelism is worker processes times `OCR_CONCURRENCY`; verify the numbers in the doc match the printed output

## 3. Test and fixture audit

- [x] 3.1 Create `docs/testing.md` with a table mapping every Phase 1 fixture and routing item (digital, scanned and mixed PDF, JPG, PNG, multi-page TIFF, multi-sheet XLSX, XLS, `;` + Latin-1 CSV, corrupt PDF, truncated image, empty file, wrong extension, routing of each file type) to the test file and test name that covers it; verify every row names a test that exists (`pytest --collect-only -q` lists it)
- [x] 3.2 Add the missing tests found by the table: wrong extension through `detect_type` and upload (a PNG named `.pdf` is stored as an image, a PDF named `.jpg` as a PDF), and a routing test that `run_pipeline` calls the PDF, image and spreadsheet ingest function for the matching `source_type`; verify they pass and update the table rows

## 4. Phase 1 gate

- [x] 4.1 Run `make lint`, `make test` (all earlier tests included), `make bench` and `openspec validate --all --strict`, and verify all pass
- [ ] 4.2 With the stack rebuilt (`make up`), upload one file of each type (digital PDF, scanned PDF, mixed PDF, JPG, PNG, multi-page TIFF, multi-sheet XLSX, XLS, `;` Latin-1 CSV) and confirm pages and text appear, statuses reach `COMPLETED`, and `ocr` events exist only for scanned content; upload a corrupt PDF, a truncated JPG, a truncated XLSX, an empty file and a wrong-extension file and confirm each fails or is rejected with its documented code; record the results in the Phase 1 section of the master plan
- [ ] 4.3 Update the master plan (`~/Desktop/personal-project/ai-document-intelligence.md`): tick every Phase 1 checkbox and the phase gate, add the daily log entry, and set the status line to Phase 1 done

## Workflow follow-up

- Archive with `/opsx:archive`, then commit in atomic commits on a `feat/ingestion-complete-phase1-ingestion` branch (create it before the first commit; do not commit on `main`).
- Push only when asked; open the PR into `main`.
