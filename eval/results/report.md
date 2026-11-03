# Evaluation report

## Conditions

| Item | Value |
|---|---|
| Run date | 2026-11-03 |
| Git commit | e9bd146 |
| Extraction model(s) | gemini-3.5-flash-lite, gemini-3.6-flash |
| Prompt version(s) | v1 |
| Embedding model | models/gemini-embedding-002 |
| Documents | 33 (31 accepted, 0 not evaluated) |
| Re-run after a provider limit | 13 |
| By category | csv 3, digital_pdf 6, failure 4, jpg 3, png 3, scanned_pdf 3, seeded_error 4, tiff 2, xls 2, xlsx 3 |
| By file type | csv 3, jpg 3, pdf 17, png 3, tiff 2, xls 2, xlsx 3 |
| Runner settings | {'concurrency': 2, 'retries': 0, 'timeout': 300.0} |

## Results

| Metric | First pass | After retry |
|---|---|---|
| Document success rate | 100.0% | 100.0% |
| Document failure rate | 6.5% | 6.5% |
| Expected failures and refusals handled as expected | 100.0% | 100.0% |
| Documents with every field correct | 86.2% | 86.2% |
| Invoice count correct | 100.0% | 100.0% |
| Line items correct (count and sum) | 94.4% | 94.4% |
| Seeded validation errors flagged (of 3) | 100.0% | 100.0% |
| Clean documents sent to review (of 26) | 0.0% | 0.0% |

Success rate is measured on documents expected to succeed (status completed or needs review);
failure rate on all accepted documents (failed or timed out). After retry equals first pass if no retry ran.

## Field accuracy (after retry)

| Field | Correct | Wrong | Missing | Invented | Accuracy | Invented rate |
|---|---|---|---|---|---|---|
| invoice_number | 35 | 1 | 0 | 0 | 97.2% | n/a |
| invoice_date | 36 | 0 | 0 | 0 | 100.0% | n/a |
| supplier_name | 35 | 1 | 0 | 0 | 97.2% | n/a |
| customer_name | 30 | 2 | 0 | 0 | 93.8% | 0.0% |
| subtotal | 22 | 1 | 0 | 1 | 95.7% | 7.7% |
| tax | 22 | 0 | 0 | 0 | 100.0% | 0.0% |
| total | 35 | 1 | 0 | 0 | 97.2% | n/a |
| currency | 35 | 1 | 0 | 0 | 97.2% | n/a |

Accuracy is correct over (correct + wrong + missing); invented rate is invented over fields whose truth is null.

## By extraction model

| Model | Documents | Every field correct | Fields not correct |
|---|---|---|---|
| gemini-3.5-flash-lite | 19 | 84.2% | 7 |
| gemini-3.6-flash | 10 | 90.0% | 1 |

The model recorded on each document's extraction. More than one row means the run spanned models.

## Processing time (seconds)

| File type | Documents | Median | 95th pct | Max |
|---|---|---|---|---|
| csv | 3 | 13.3 | 16.4 | 16.4 |
| digital_pdf | 10 | 3.1 | 35.6 | 35.6 |
| failure | 2 | 1.4 | 1.5 | 1.5 |
| jpg | 3 | 3.1 | 3.1 | 3.1 |
| png | 3 | 4.3 | 6.3 | 6.3 |
| scanned_pdf | 3 | 3.1 | 16.2 | 16.2 |
| tiff | 2 | 3.1 | 18.4 | 18.4 |
| xls | 2 | 3.0 | 19.3 | 19.3 |
| xlsx | 3 | 17.3 | 21.4 | 21.4 |

| Stage | Documents | Median | 95th pct | Max |
|---|---|---|---|---|
| embed | 23 | 0.9 | 1.1 | 1.1 |
| extract | 29 | 2.4 | 16.9 | 19.3 |
| ingest | 29 | 0.1 | 0.4 | 0.6 |
| ocr | 11 | 0.5 | 1.8 | 1.8 |

Total wall time 396 s for 31 accepted documents: 4.7 documents per minute.

## Failure analysis

Every document ended as its ground truth says.

Fields not correct: 8

| File | Invoice | Field | Result | Expected | Returned |
|---|---|---|---|---|---|
| image-jpg-01.jpg | EV-1011 | customer_name | wrong | Contoso Retail GmbH | Contoso Retal1l GmbH |
| image-jpg-03.jpg | EV-1013 | invoice_number | wrong | EV-1013 | Ev-101) |
| image-jpg-03.jpg | EV-1013 | supplier_name | wrong | Orbit Engineering Co | Orbit Engiaseriag Co |
| image-jpg-03.jpg | EV-1013 | customer_name | wrong | Contoso Retail GmbH | DIIL Coe Contos Retail Gmpa |
| image-jpg-03.jpg | EV-1013 | subtotal | wrong | 3961.51 | 396381 |
| image-jpg-03.jpg | EV-1013 | total | wrong | 3961.51 | 396392 |
| image-jpg-03.jpg | EV-1013 | currency | wrong | GBP | USD |
| sheet-csv-02.csv | EV-1021 | subtotal | invented | None | 207.65 |

## Commentary

**What the run shows.** All 29 documents expected to succeed finished (`COMPLETED` or `NEEDS_REVIEW`), the two refusals and the two intended failures ended as their labels say, and no document failed unexpectedly. The 6.5% failure rate is those two intended failures (the corrupt and the encrypted PDF, 2 of 31 accepted documents). 25 of 29 documents (86.2%) have every field right, and the invoice count is right on every document, including the PDF holding three invoices.

**The run used two models.** The extraction model was changed part-way through because of the provider's free-tier limit (20 requests per day per model). 19 documents were extracted by `gemini-3.5-flash-lite` and 10 by `gemini-3.6-flash` (configured as `gemini-3.5-flash` earlier; the stored model name is `gemini-3.6-flash`). The figures above are for the mix, and the by-model table shows the split. The samples are too small to rank the models: the difference between 84.2% and 90.0% is one document.

**Provider limits.** 13 documents were first refused by the provider's daily limit. They were left out of the figures while refused and re-run later with `--resume`; each is counted by its re-run, which is why first pass and after retry are equal. The run took 396 s in total over several sessions.

**Where the errors are (8 fields in 4 documents).**
- **Image quality is the main source.** `image-jpg-03.jpg`, the lowest-quality image (55% size, heavy JPEG compression), accounts for 6 of the 8 wrong fields. The OCR text was garbled and the extractor copied what it read, as its prompt tells it to: the invoice number came back as `Ev-101)`, the supplier as `Orbit Engiaseriag Co`, the subtotal as `396381` instead of `3961.51` (the decimal point lost) and the currency as `USD` instead of `GBP`.
- **That document was not sent to review.** It ended `COMPLETED`; its only finding was the `ungrounded_field` warning. So damaged text can produce wrong values, including an amount off by a factor of 100, that the validation rules do not catch. This is the most important weakness in the results. A possible fix, not done here, is to send pages with low OCR confidence to review.
- `image-jpg-01.jpg`, a cleaner image, had one OCR misreading in the customer name (`Contoso Retal1l GmbH`) and also ended `COMPLETED`. Small OCR errors in names pass silently too.
- **One invented value.** `sheet-csv-02.csv` returned a subtotal of `207.65` where the label is null: the file has one line amount of 207.65 and no subtotal column, and the extractor reported the line amount as the subtotal. With a single line item the number equals the real subtotal, so it is arguably right in substance, but under the "never infer" rule it counts as invented. It is 1 of the 13 spreadsheet subtotals that should be null (7.7%); the other 12 were left null.

**Validation worked on the cases seeded.** Both documents with a wrong total were flagged `total_mismatch` and the second copy of the duplicate was flagged `duplicate_invoice`: 3 of 3. None of the 26 clean documents was sent to review. `duplicate-b.pdf` also received a `future_date` finding because the fixture dates it 2026-12-01, after the run date; that finding is correct and is a quirk of the fixture.

**Time.** A typical PDF or image took about 3 seconds end to end (median 3.1 s for digital PDFs, JPG, scanned PDFs and TIFF). Spreadsheets were slower in this run (median 13.3 s for CSV and 17.3 s for XLSX) and the slowest document took 35.6 s. By stage: ingest median 0.1 s, OCR 0.5 s, extraction 2.4 s (95th percentile 16.9 s), embedding 0.9 s. The long tails most likely include the worker waiting and retrying after the provider's rate limits, which was not measured separately, so treat the slow times as an upper bound for the provider's behaviour, not a property of the pipeline. Throughput was 4.7 documents per minute at concurrency 2, including those waits.

**How to read this.** The documents are synthetic, English and cleanly laid out, there are 29 of them, and this is one run. The results show that the pipeline runs end to end, that expected failures and refusals are handled, and that validation catches arithmetic errors and duplicates. They do not show how accurate the system is on real invoices, where the image-quality effect above is likely to matter more. The report records the commit `e9bd146`; the evaluation code itself was uncommitted when the run was made.

## Limits of this evaluation

- **The data is synthetic.** The documents are drawn by code from known values, in English, with clean
  layouts. Scores are an upper bound for real invoices; this report makes no claim about real-world accuracy.
- **The set is small** (see the counts above). A difference of one document moves a rate by several points.
- **The generator and the system share an author.** The extractor was not tested on layouts it was never
  shown, and the set was not used to tune the prompt, model or rules.
- **One run.** The model is not deterministic and reruns can differ by a point or two. No averaging was done.
- **Provider limits affect failures and times.** A rate limit or a busy model ends a document as failed for
  a reason that is not the extractor's; first-pass and after-retry results are shown separately.
- **Spreadsheets carry a tax rate and a total, not a subtotal or tax amount**, so those fields are expected
  to be null there and anything returned counts as invented.
