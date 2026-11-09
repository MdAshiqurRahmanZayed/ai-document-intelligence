# Design

## Context

The pipeline and API are finished and manually tested. Facts the evaluation relies on, taken from the code and `docs/api.md`:

- `POST /api/v1/documents` takes the form field `files`; each file reports `accepted`, `duplicate` or `rejected` with a reason (an empty file is rejected as `empty_file`, a corrupt or renamed file as `unsupported_type`; neither becomes a document).
- A document ends `COMPLETED`, `NEEDS_REVIEW` or `FAILED` (with `error_code`, for example `pdf_encrypted` or `pdf_corrupt`). `GET /documents/{id}` returns the status and `events` with stage, status, `duration_ms` and attempt. `GET /documents/{id}/result` returns the invoices with normalised `data` (amounts as decimal strings, ISO dates), confidence, grounding and validation findings.
- `backend/scripts/make_sample_documents.py` already draws invoices (digital PDF, scanned image, spreadsheets) from an `Invoice` dataclass with known values. Its `lines()` always prints the customer and the tax, so it cannot yet make an invoice with a field absent.
- The model call is rate limited and the free-tier key can return 429 or 503, so failures can come from the provider and not the extractor.
- `eval/` does not exist. `.gitignore` already ignores `eval/dataset/documents/` and keeps `eval/dataset/ground_truth/`. `make eval` is a placeholder. Backend tests run in a container that only has `backend/`; `web-test` already shows the pattern for mounting another folder read-only.

See proposal.md for the motivation and scope.

## Goals / Non-Goals

**Goals:**
- Real, repeatable numbers for accuracy, success and failure rates and timing, measured through the same API a user uses.
- Wrong, missing and invented values kept apart, because "never invent values" is a stated requirement.
- A report that states its conditions and limits plainly.

**Non-Goals:**
- No tuning of the prompt, model or rules against this set.
- No real-world dataset, though the format must accept one.
- No end-to-end load test at 1000 pages, and no large dataset: the size is set by the model quota.

## Decisions

1. **Synthetic labelled dataset with known truth, built by code.** Real labelled invoices are not available. Generating from known values gives exact ground truth for free and is deterministic. The report says it is synthetic, so its scores are an upper bound for real documents. Alternative: hand-label a few downloaded real receipts. Rejected as the main set (labelling by hand costs hours); the format accepts them: a real file goes in `eval/dataset/documents/` with a `real-<name>.json` label in `ground_truth/` (the builder never deletes `real-*` labels), and it is scored with the rest.
2. **Ground truth committed, documents generated.** `eval/dataset/ground_truth/*.json` (one file per document, plus a `manifest.json` with counts per category) is committed. `eval/build_dataset.py` writes the documents to the already-ignored `eval/dataset/documents/`. Alternative: commit the binary files. Rejected: large, and the builder is the source of truth.
3. **Reuse the sample generator.** Refactor `make_sample_documents.py` so `Invoice`, `lines`, `pdf_text`, `scan` and the spreadsheet writers can be imported, with the same output as before. Add optional flags to `lines()` to leave out a field, so a document can truly not state a customer, tax or due date. The builder adds image degradation levels (clean, tilted, blurred and noisy, low resolution and heavy JPEG) and the four failure files. Alternative: a second generator. Rejected: duplicated drawing code.
4. **Three kinds of expected outcome.** `success`, `failed:<error_code>` (encrypted PDF, corrupt PDF) and `rejected:<reason>` (empty file, renamed unsupported file). Success rate is measured on documents expected to succeed; failure rate on all accepted documents; refusals and expected failures are scored on whether the code matches.
5. **Run through the public API with httpx, from the host.** `eval/run_eval.py` uploads in small batches, polls `GET /documents/{id}` every second until a final status or a per-document timeout (default 300 s), then reads `/result`. It times each document with a monotonic clock from the upload response to the final status, and takes stage durations from `events`. It reads `API_URL` (default `http://localhost:8000`) and `API_KEY` from the environment. Run with `cd backend && uv run python ../eval/run_eval.py` (httpx is already a dependency). Alternative: query the database. Rejected: it would skip the API, and the brief asks for the system's behaviour.
6. **Guard against a dirty database.** Duplicate detection and "already uploaded" depend on what is stored, so the runner stops if `GET /documents` is not empty, unless `--allow-nonempty`. Dataset invoice numbers use their own prefix to limit accidental clashes.
7. **First pass and retry reported apart.** Provider errors (429, 503) end documents as `FAILED` for reasons that are not the extractor's fault. `--retries N` re-queues failed documents through `POST /documents/{id}/reprocess` and records both the first-pass and the after-retry outcome. Headline rates are first pass; the retry figures are shown beside them. Nothing is hidden or relabelled.
8. **Scoring rules, fixed and documented.** Amounts correct within 0.01; dates equal as ISO strings; invoice numbers equal ignoring case, spaces and punctuation; supplier and customer equal ignoring case, punctuation and company forms (Ltd, Inc, GmbH, AB, AS), reusing the normalisation of cross-verification where it can be imported; currency equal. For each field: correct, wrong, missing or invented. Line items: count equal, and sum of amounts within 0.01. Document exact match: every field of every invoice correct. A document with several invoices matches predicted to expected by invoice number first, then order. Validation: for seeded errors, was the expected finding code present (recall); for clean invoices, was any error-severity finding raised (false alarm rate).
9. **Time metrics.** Per document: end-to-end seconds. Per stage (`ingest`, `ocr`, `extract`, `embed`): `duration_ms` from events. Median, 95th percentile and maximum by file type (digital PDF, scanned PDF, image, spreadsheet) and by stage, plus total wall time and documents per minute. The report notes the provider limits and concurrency used, since both affect the numbers.
10. **Pure scorer, thin runner, template report.** `eval/scoring.py` takes expected and actual dicts and returns counts, so it needs no network. The runner only collects and saves `results.json` (raw outcomes, timings, extracted data, settings, model IDs, prompt version taken from `/result`, git commit). `eval/report.py` renders `report.md` from `results.json`; `run_eval.py --rescore` calls it without the API. The failure analysis section is generated from the data (lowest-scoring fields, each failed document with its code, wrong fields with expected and actual values); the written commentary is added by hand after reading the results and cites those same items.
11. **Tests without a model.** Scoring tests use fixed dicts (tolerance, null handling, wrong versus missing versus invented, multi-invoice matching). Runner tests use `httpx.MockTransport` for upload refusals, polling, timeout, retry and the non-empty guard. Report tests render a fixture `results.json` and compare the key numbers. They live in `eval/tests/` and run in the backend test container with `eval/` mounted read-only (as `web-test` does with `docs/`), so `make test` stays Docker-only. They never touch the database, so they must not depend on the backend test database fixtures.
12. **Sized for a limited quota, with partial runs.** The dataset is about 33 documents, not 50, and has no 60-page PDF (it alone costs about ten extraction calls, and `docs/performance.md` already covers large-file ingest). Planned counts: digital PDF 6 (one with 3 invoices), scanned PDF 3, JPG 3, PNG 3, TIFF 2, CSV 3, XLSX 3 (one with several sheets), XLS 2, seeded errors 4 PDFs (two wrong totals, one duplicate pair), and 4 files that must be refused or fail (encrypted PDF, corrupt PDF, empty file, renamed unsupported file), which cost no model calls. Quality levels and absent fields are spread across these counts. The runner defaults to concurrency 2 and one retry round. `--only <group>` runs one group (pdf, image, spreadsheet, failures) and `--resume` skips documents already in `results.json`; results are saved after every document, so an interruption loses nothing. With `--resume`, the non-empty-database guard accepts documents whose ids are all recorded in `results.json` and stops on any unknown one. The model is not switched to a cheaper one: the report evaluates the model the system runs with.
13. **`make eval`** runs the builder if the documents are missing, then the runner, then writes the report. It needs the stack up and a key, and prints that. It is not part of `make test` or `make check` because it calls the real model.

## Risks / Trade-offs

- **Synthetic data flatters the system.** Generated pages are clean and consistent, so accuracy will look better than on real invoices. Mitigated by stating it up front, adding degradation levels, absent-field and error cases, and leaving room for real documents. The report must not claim real-world accuracy.
- **Same author for generator and system.** Both come from the same code family, so the extractor is not tested on layouts it was never shown. Stated as a limit.
- **Provider limits distort results.** 429 and 503 produce failures and long times that are not about the extractor. Mitigated by the first-pass and retry split, recording error codes, and a modest concurrency.
- **Run cost and time.** About 33 documents mean roughly 25 to 30 extraction calls plus embeddings, likely 5 to 10 minutes under the rate limit, and less quota use on the free tier. A run is done by hand, once for the committed results and again only when needed.
- **Non-deterministic model.** A rerun can differ slightly. The report records the single committed run and says reruns may differ by a point or two; it does not average runs.
- **Mount path for tests.** Running the eval tests in the backend container assumes `eval/` can be mounted and imported without the application's test fixtures. If that proves awkward, fall back to running them with `uv run pytest ../eval/tests` on the host and document it.
- **Refactoring the sample generator** could change the committed sample output. Mitigated by regenerating the samples before and after and comparing the files.

## Open Questions

- Whether to also include a handful of real, hand-labelled documents. Default: not now. The builder keeps `real-*` labels and the runner reads every label, so they can be added later without code changes.
