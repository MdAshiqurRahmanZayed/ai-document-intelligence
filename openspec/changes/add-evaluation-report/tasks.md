# Tasks

## 1. Reusable generator

- [x] 1.1 Snapshot the current sample output: regenerate `backend/tests/fixtures/samples/` and save a checksum list (scratch, not committed). Verify: the list has one line per file.
- [x] 1.2 Refactor `backend/scripts/make_sample_documents.py` so `Invoice`, `lines`, `pdf_text`, `scan`, `rows` and the spreadsheet writers are importable without side effects, and add optional flags to `lines()` (and the spreadsheet rows) to leave out the customer, tax or due date. Verify: regenerate and compare with the 1.1 checksums (identical); `ruff check` and `ruff format --check` pass.

## 2. Dataset

- [x] 2.1 Define the ground-truth JSON format in `eval/README.md`: per document `file`, `category`, `expected_outcome` (`success`, `failed:<code>` or `rejected:<reason>`), `invoices[]` with the API's `data` fields as strings and `null` for absent, and `expected_findings[]`. Verify: the README shows one example of each outcome kind.
- [x] 2.2 Write `eval/build_dataset.py` that generates about 33 documents and their ground truth (digital PDF 6, scanned PDF 3, JPG 3, PNG 3, TIFF 2, CSV 3, XLSX 3, XLS 2, seeded errors 4, failures 4): one digital PDF holds three invoices; scanned PDFs and JPG, PNG and TIFF images are spread over the quality levels (clean, tilted, blurred and noisy, low resolution); XLSX has one multi-sheet file; a few invoices leave out the customer, tax or due date; the seeded errors are two wrong totals (one a line-sum mismatch) and one duplicate pair; the failures are an encrypted PDF, a corrupt PDF, an empty file and a renamed unsupported file. It also writes `manifest.json` with counts per category and type. It seeds all randomness. Verify: running it prints the counts; every ground-truth file has a document and the reverse.
- [x] 2.3 Check determinism and coverage: run the builder twice and compare checksums, and assert coverage in a test (`eval/tests/test_dataset.py`): at least 30 documents, every file type, every category, absent fields are `null`, expected outcomes for the failure files match `docs/api.md` codes. Verify: the test passes; two builds give identical checksums.
- [x] 2.4 Commit `eval/dataset/ground_truth/` and `manifest.json`; confirm `eval/dataset/documents/` stays ignored. Verify: `git status` shows ground truth added and no generated documents.

## 3. Scoring

- [x] 3.1 Write `eval/scoring.py` with the comparison rules (amount tolerance 0.01, ISO dates, normalised invoice numbers and names ignoring company forms, currency) and the per-field result correct, wrong, missing or invented. Reuse the backend's name normalisation if it can be imported without the app. Verify: unit tests in `eval/tests/test_scoring.py` cover each rule and each of the four results.
- [x] 3.2 Add invoice matching (by number, then order), line-item count and sum, document exact match, invoice-count accuracy, validation recall and false alarms, and the document outcome rules (success rate, failure rate, expected-failure and refusal match). Verify: tests with fixed inputs for a multi-invoice document, a missing invoice, a seeded error caught and missed, a clean invoice flagged, and a refusal.
- [x] 3.3 Add timing statistics (median, 95th percentile, maximum by file type and stage, wall time, documents per minute). Verify: tests with known durations give the expected percentiles, including a single value and an empty group.

## 4. Runner and report

- [x] 4.1 Write `eval/run_eval.py`: read `API_URL` and `API_KEY`, stop if the database holds documents (unless `--allow-nonempty`), upload in small batches, record refusals, poll to a final status with a per-document timeout, fetch `/result`, and save `eval/results/results.json` with raw outcomes, timings, extracted data, settings, model IDs, prompt version and git commit. Add `--retries N` (reprocess failed documents, keep first-pass and after-retry outcomes; default 1), `--concurrency` (default 2), `--timeout`, `--only <group>` (pdf, image, spreadsheet, failures) and `--resume` (skip documents already in `results.json`; save results after every document). Verify: tests with `httpx.MockTransport` cover a clean run, a refused file, a failed document, a timeout, the retry path, the non-empty guard, a run limited to one group, and a resume after an interruption.
- [x] 4.2 Write `eval/report.py` and `--rescore` so `report.md` is rendered from `results.json` with no API or key: conditions, metrics tables, timing tables, failure analysis generated from the data, limits section. Verify: a test renders a fixture `results.json` and checks the key numbers and sections; running `--rescore` offline works.
- [x] 4.3 Make the evaluation tests run in Docker: mount `./eval` read-only into `backend-test` in `docker-compose.yml` and make sure they do not need the test database. Verify: `docker compose --profile test run --rm backend-test pytest /eval/tests` passes; if the mount does not work, document `cd backend && uv run pytest ../eval/tests` instead and say why.
- [x] 4.4 Include the eval folder in lint: `ruff check` and `ruff format --check` over `eval/` with the backend settings (line length 100). Verify: both pass, wired into `make lint`.

## 5. Make target and docs

- [x] 5.1 Implement `make eval` (build the documents if missing, run, write the report) and a `make eval-report` for `--rescore`; print that the stack, an empty database and a key are needed. Verify: `make help` lists both; running `make eval` without the stack gives a clear message, not a traceback.
- [x] 5.2 Write `eval/README.md`: what is measured and how, the scoring rules, how to run, how to add real labelled documents under `eval/dataset/real/`, and the limits. Verify: every command in it is run once.

## 6. The real run

- [x] 6.1 The user starts from a clean stack (`docker compose --profile monitoring down -v && make up && make migrate`) with a working `GOOGLE_API_KEY`, then runs `make eval`, in parts if the quota is tight (`--only failures` first, then `--only spreadsheet`, `--only pdf`, `--only image`, using `--resume` after any interruption). Verify: `eval/results/results.json` and `report.md` exist and `report.md` lists the models, prompt version, dataset counts, date and commit.
- [x] 6.2 Read the report against the raw results and write the commentary: biggest error sources, each failed document with its recorded code, wrong fields with expected and actual values, and the effect of provider errors. Verify: every example cited exists in `results.json`; no figure is typed by hand.
- [x] 6.3 Update `README.md` (replace the "No evaluation" limit with the measured results and a link), `docs/testing.md`, and the AI disclosure if needed. Verify: each figure quoted equals the figure in `report.md`; `make eval` text in the README matches the Makefile.

## 7. Finish

- [x] 7.1 Run `openspec validate --all --strict` and `make check`. Verify: both pass.
- [x] 7.2 Commit atomically (`refactor(repo)` for the generator, `feat(eval)` for dataset, scoring, runner and report with tests, `docs(eval)` or `docs(repo)` for the results and README, `docs(openspec)` for the change), no co-author trailers, branch `feat/eval-add-evaluation-report`; push and open the PR only when asked. Verify: `git log --oneline` shows conventional messages.
