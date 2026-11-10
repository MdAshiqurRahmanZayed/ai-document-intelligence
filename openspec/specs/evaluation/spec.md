# evaluation Specification

## Purpose
Defines how the system's extraction accuracy, success and failure rates and processing time are measured on a labelled dataset through the real pipeline, and how the results are reported so a reviewer can trust and reproduce them.

## Requirements

### Requirement: Labelled dataset
The repository SHALL contain ground truth for a dataset of at least 30 documents covering every accepted file type (digital PDF, scanned PDF, JPG, PNG, TIFF, XLSX, XLS, CSV), several image quality levels, spreadsheets with more than one sheet, PDFs holding several invoices, invoices with fields deliberately absent, invoices with seeded validation errors, duplicate invoices, and files that must be refused or must fail (encrypted and corrupt PDFs, an empty file, a renamed unsupported file). Each file SHALL have a recorded expected outcome (success, failure with an error code, or refusal at upload with a reason), and each expected invoice SHALL record its true values, using `null` for a field the document does not state. The documents SHALL be generated deterministically from the ground truth by a script, so the same inputs always give the same files.

#### Scenario: Coverage
- **WHEN** the ground truth is read
- **THEN** it contains at least one document for each file type and each category listed above, and a count per category

#### Scenario: Deterministic generation
- **WHEN** the dataset builder is run twice
- **THEN** the generated documents are byte-identical and every ground-truth entry has a matching file

#### Scenario: Absent fields are labelled null
- **GIVEN** a generated invoice that does not state a customer name
- **WHEN** its ground truth is read
- **THEN** `customer_name` is `null`

#### Scenario: Expected failures and refusals
- **GIVEN** an encrypted PDF and an empty file in the dataset
- **WHEN** their ground truth is read
- **THEN** the encrypted PDF is expected to end `FAILED` with the error code the API documents for encrypted PDFs, and the empty file is expected to be refused at upload with the documented reason

### Requirement: Evaluation run through the real pipeline
The evaluation runner SHALL upload the dataset through the public API, record every file the API refuses, wait for every accepted document to reach a final status (`COMPLETED`, `NEEDS_REVIEW` or `FAILED`) or a timeout, and record for each document its outcome, error code, end-to-end time, per-stage durations from the processing events, and the extracted invoices. It SHALL use the real extraction model and SHALL refuse to run against a database that already holds documents unless told to. It SHALL allow a run to be limited to a group of files and to be resumed from saved results, so documents already finished are not uploaded or sent to the model again.

#### Scenario: Full run
- **GIVEN** the stack is running with a model key and an empty database
- **WHEN** the runner is started
- **THEN** every dataset file is uploaded, every document is followed to a final status, and the raw per-document results are saved

#### Scenario: Slow document
- **WHEN** a document does not reach a final status within the timeout
- **THEN** it is recorded as timed out, counted as a failure, and the run continues

#### Scenario: Non-empty database
- **GIVEN** the database already holds documents
- **WHEN** the runner is started without the override
- **THEN** it stops with a message and uploads nothing

#### Scenario: Resume after an interruption
- **GIVEN** a run stopped after some documents had finished and their results were saved
- **WHEN** the runner is started again with the resume option
- **THEN** documents already recorded are skipped, the remaining ones are processed, and the final results hold every document once

#### Scenario: Run one group
- **WHEN** the runner is started limited to one group of files (for example the PDFs)
- **THEN** only those files are uploaded, and their results are merged into the saved results

#### Scenario: First pass and retry
- **WHEN** documents fail and a retry is requested
- **THEN** both the first-pass outcome and the outcome after retry are recorded and reported separately

### Requirement: Measured metrics
The evaluation SHALL report, from the saved results: per-field extraction accuracy for invoice number, invoice date, supplier name, customer name, subtotal, tax, total and currency, with each field counted as correct, wrong, missing (extracted as `null` when the truth has a value) or invented (extracted with a value when the truth is `null`); line-item accuracy (count and sum); the share of invoices with every field correct; invoice-count accuracy; validation detection (seeded errors flagged) and false alarms (clean invoices flagged); document success rate and failure rate; and processing time as median, 95th percentile and maximum by file type and by stage, with total wall time and documents per minute. Comparisons SHALL be defined and documented: amounts within 0.01, dates as ISO 8601, names ignoring case, punctuation and company forms.

#### Scenario: Wrong, missing and invented are separate
- **GIVEN** the truth has a supplier and the system returns a different supplier
- **WHEN** the metrics are computed
- **THEN** the field counts as wrong, not as missing

#### Scenario: Invented value
- **GIVEN** the truth has no tax and the system returns a tax amount
- **WHEN** the metrics are computed
- **THEN** the field counts as invented

#### Scenario: Amount tolerance
- **GIVEN** the truth total is 120.00 and the system returns 120.01
- **WHEN** the metrics are computed
- **THEN** the total counts as correct

#### Scenario: Success and failure rates
- **WHEN** the metrics are computed
- **THEN** the success rate is the share of documents expected to succeed that reached `COMPLETED` or `NEEDS_REVIEW`, the failure rate is the share of all documents that ended `FAILED` or timed out, and the share of expected failures and refusals that ended with the expected error code or reason is reported; a file refused at upload counts as a refusal, not as a failed document

#### Scenario: Timing by type and stage
- **WHEN** the metrics are computed
- **THEN** median, 95th percentile and maximum time are given per file type and per stage, from timings recorded by the runner and the processing events

### Requirement: Committed, honest report
The evaluation SHALL produce `eval/results/report.md` and `eval/results/results.json`, committed to the repository. The report SHALL state the model IDs, prompt version, dataset size and composition, run date, git commit and runner settings; present the metrics above; analyse the failures from the actual results with examples; and state the limits of the evaluation, including that the dataset is synthetic and small and that it was not used to tune the system.

#### Scenario: Report records its conditions
- **WHEN** the report is opened
- **THEN** it names the extraction and embedding models, the prompt version, the number of documents by category, the date and the commit

#### Scenario: Failure analysis comes from results
- **WHEN** the report discusses failures
- **THEN** each example cites a document and its recorded error or wrong field, and no failure is described that is not in the results

#### Scenario: Limits stated
- **WHEN** the report is opened
- **THEN** it states that the data is synthetic, English, small, and generated by the same code family as the development samples

### Requirement: Reproducible
`make eval` SHALL run the evaluation from a running stack and write the results and report. The report SHALL also be rebuildable from the saved `results.json` without the API or a model key.

#### Scenario: Rebuild from saved results
- **GIVEN** `eval/results/results.json` exists
- **WHEN** the rescore option is used with no stack running
- **THEN** `report.md` is regenerated with the same numbers

#### Scenario: Numbers elsewhere match the report
- **WHEN** the README or other docs quote an evaluation figure
- **THEN** it equals the figure in `eval/results/report.md`

### Requirement: Scoring and runner are tested
The scoring, the runner's polling and timeout handling, and the report rendering SHALL have automated tests that need no model and no running stack.

#### Scenario: Tests run offline
- **WHEN** the evaluation tests are run
- **THEN** they pass with no network access, using fixed inputs and a stub API
