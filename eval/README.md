# Evaluation

Measures extraction accuracy, document success and failure rates and processing time on a labelled dataset, through the real API and the real model. Results: [results/report.md](results/report.md).

The dataset is **synthetic**: documents are drawn by code from known values, so the true answer is exact. Scores are an upper bound for real invoices. See the limits section of the report.

## What is measured

- **Per field** (invoice number, date, supplier, customer, subtotal, tax, total, currency): correct, wrong, missing (null returned, truth has a value) or invented (value returned, truth is null).
- **Documents:** every field right, invoice count right, line items right (count and sum), success rate, failure rate, expected failures and refusals handled as expected.
- **Validation:** seeded errors flagged, and clean documents wrongly sent to review.
- **Time:** median, 95th percentile and maximum seconds by file type and by stage, total wall time, documents per minute.

Comparison rules (`scoring.py`): amounts within 0.01, dates as ISO strings, invoice numbers ignoring case, spaces and punctuation, names ignoring case, punctuation and company forms (Ltd, Inc, GmbH...), currency ignoring case. Success rate is over documents expected to succeed (`COMPLETED` or `NEEDS_REVIEW`); failure rate is over all accepted documents (`FAILED` or timed out). Headline numbers are first pass; the after-retry column shows documents that succeeded when re-queued once (a rate limit or busy model is not the extractor's fault).

## Files

| Path | What |
|---|---|
| `build_dataset.py` | Generates the documents into `dataset/documents/` (git-ignored) and the labels into `dataset/ground_truth/` (committed). Same bytes every run. |
| `dataset/ground_truth/*.json` | One label per document, and `dataset/manifest.json` with the counts |
| `run_eval.py` | Uploads the dataset, follows each document, saves `results/results.json` and `results/report.md` |
| `scoring.py`, `report.py` | Scoring and report rendering (no network) |
| `results/commentary.md` | Optional hand-written commentary, appended to the report |
| `tests/` | Tests for all of the above (no model, no stack): `make test` |

## Ground truth format

One JSON file per document, named `<file>.json`:

```json
{
  "file": "digital-01.pdf",
  "category": "digital_pdf",
  "group": "pdf",
  "expected_outcome": "success",
  "expected_findings": [],
  "invoices": [
    {
      "invoice_number": "EV-1000", "invoice_date": "2026-09-02", "supplier_name": "Northwind Supplies Ltd",
      "customer_name": null, "subtotal": "512.40", "tax": "117.85", "total": "630.25", "currency": "EUR",
      "line_items_count": 3, "line_items_sum": "512.40"
    }
  ]
}
```

- `null` means the document does not state the field. A spreadsheet states a tax rate and a total but no subtotal or tax amount, so those are `null` for spreadsheets.
- `expected_outcome` is `success`, `failed:<error_code>` (the document ends `FAILED` with that code, for example `failed:pdf_encrypted`) or `rejected:<reason>` (the API refuses it at upload, for example `rejected:empty_file`). Files that must fail have an empty `invoices` list.
- `expected_findings` lists validation codes that must be raised (for example `["total_mismatch"]`).
- `after` (optional) names a file that must finish first: `duplicate-b.pdf` follows `duplicate-a.pdf` so the duplicate is found.
- `group` is `pdf`, `image`, `spreadsheet` or `failures`, for `--only`.

## Run it

Needs the stack up (`make up`, `make migrate`), a working `GOOGLE_API_KEY` in `.env` (the runner also reads `API_KEY` and `API_URL` from `.env`, or from the environment), **an empty database** (the run stops otherwise), and [uv](https://docs.astral.sh/uv/) on the host.

```bash
make eval                                  # build the documents if missing, run, write results and report
make eval ARGS="--only failures"           # one group: pdf, image, spreadsheet or failures
make eval ARGS="--only pdf --resume"       # skip finished documents; re-run those the provider refused
make eval-report                           # rebuild report.md from results.json (no stack, no key)
```

Options (`run_eval.py --help`): `--retries N` (default 1), `--concurrency N` (default 2), `--timeout SECONDS` (default 300), `--stop-after N` (stop after N failures in a row, default 3; usually a provider quota), `--allow-nonempty`. A document that fails only because the provider refused it (quota, rate limit, outage: the recorded error names it) is **not evaluated**: it is left out of every figure and listed in the report, and `--resume` reprocesses it. It prints one line per finished document. On a free-tier key the quota can be as low as 20 requests per day per model, which a full run exceeds: see the report's limits. Results are saved after every document, so an interrupted run loses nothing; rerun with `--resume`. A full run makes about 25 to 30 extraction calls plus embeddings, so mind your model quota: run the groups one at a time. It is never part of `make test`.

## Add real documents

Put the file in `dataset/documents/` and a label `dataset/ground_truth/real-<name>.json` in the format above (the builder never deletes `real-*` labels). It is then run and scored with the rest.
