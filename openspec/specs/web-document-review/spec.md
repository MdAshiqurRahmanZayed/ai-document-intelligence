# web-document-review Specification

## Purpose
Lets a person follow documents through processing, inspect what was extracted next to the original file, understand validation findings, correct values, and recover failed documents.

## Requirements

### Requirement: Document list with live status
The documents page SHALL list documents newest first with filename, a status badge, page count, and the supplier, number and total of each current invoice. It SHALL offer filters for status, supplier, invoice number, date range, amount range and currency, and a control to load the next page. While any listed document is `UPLOADED`, `QUEUED` or `PROCESSING` the page SHALL refresh the list automatically, and SHALL stop when none is.

#### Scenario: Status updates by itself
- **GIVEN** a listed document in `PROCESSING`
- **WHEN** the API later reports it as `COMPLETED`
- **THEN** the page shows the new badge without a manual reload

#### Scenario: No polling when idle
- **GIVEN** every listed document is `COMPLETED`, `NEEDS_REVIEW` or `FAILED`
- **THEN** the page does not refresh on a timer

#### Scenario: Filter
- **WHEN** a person selects the status `NEEDS_REVIEW`
- **THEN** only documents in that status are listed

#### Scenario: Load more
- **GIVEN** the API returns a `next_cursor`
- **WHEN** the person asks for more
- **THEN** the next page is added after the current items without repeating any

### Requirement: Processing progress
For each document that is not finished, the list and the detail page SHALL show a progress bar with a percentage and the name of the current step. The percentage SHALL be the share of the document's expected steps that have finished, taken from its status and processing history, not an estimate of time. The expected steps are: uploaded, reading the file, text recognition (only for documents with scanned pages or images), extracting invoices (only when extraction is enabled), and done. A finished document SHALL show a final state instead of a bar: complete, needs review, or failed with the step that failed. The detail page SHALL show the steps as a sequence marking each as waiting, running, done or failed, with its duration when known.

#### Scenario: Scanned document in progress
- **GIVEN** a scanned PDF whose reading step finished and whose text recognition is running
- **THEN** the bar shows 40% and the label "Recognising text"

#### Scenario: Spreadsheet skips recognition
- **GIVEN** a spreadsheet whose reading step finished and whose extraction is running
- **THEN** the steps shown are uploaded, reading, extracting, done, and the bar shows 50%

#### Scenario: Queued
- **GIVEN** a `QUEUED` document with no history yet
- **THEN** the bar shows its first step as "Waiting for a worker" at a low percentage, not 0% and not stuck-looking

#### Scenario: Failed step
- **GIVEN** a document whose text recognition failed
- **THEN** the sequence marks that step failed with the error message and later steps stay waiting, and no progress bar is shown

#### Scenario: Retry visible
- **GIVEN** a step with a second attempt in its history
- **THEN** the step shows "attempt 2"

#### Scenario: Finished
- **WHEN** the document becomes `COMPLETED`
- **THEN** the bar is replaced by "Complete" and every step is marked done

### Requirement: Document detail
The document page SHALL show the original file (PDF pages or the image) beside the extracted invoice, the processing history (stage, outcome, duration, attempt), and, when the document failed, the error code and message. A document with several invoices SHALL show each of them. Each invoice SHALL show its fields, line items, and per-field confidence and source quote when available.

#### Scenario: Viewer beside result
- **WHEN** a person opens a processed PDF
- **THEN** the page shows the PDF and the extracted invoice side by side

#### Scenario: File without a preview
- **WHEN** the document is a spreadsheet
- **THEN** the page offers the original as a download link and says it cannot be previewed, instead of showing a viewer

#### Scenario: Several invoices
- **WHEN** the result holds two invoices
- **THEN** both are shown, in invoice order, each with its own findings

#### Scenario: Not extracted yet
- **WHEN** the document has no invoices because extraction is disabled or not finished
- **THEN** the page says so and does not show an empty form

#### Scenario: Unknown document
- **WHEN** the API answers 404
- **THEN** the page shows "document not found" with a link to the list

### Requirement: Validation findings
The detail page SHALL list every finding of each invoice and of the document, with severity (error or warning) shown by colour and text, the message, and the field concerned. A finding with a field SHALL mark that field in the form. A duplicate finding SHALL link to the related document.

#### Scenario: Error marks its field
- **GIVEN** a `total_mismatch` error on `total`
- **THEN** the total input is marked and the finding is listed with its message

#### Scenario: Severity visible without colour
- **THEN** each finding says "error" or "warning" in text

#### Scenario: Duplicate link
- **GIVEN** a `duplicate_invoice` finding with a related document
- **THEN** the finding links to that document

### Requirement: Correct values
The detail page SHALL let a person edit the invoice fields (invoice number, date, supplier, customer, subtotal, tax, total, currency, line items) and save them as one correction with a name for the audit trail. It SHALL check in the browser that dates are dates and amounts are numbers before sending, send only the changed fields, and after saving show the updated invoice, its new findings and the new document status. A correction rejected by the API SHALL show the API's message at the named field and keep what the person typed.

#### Scenario: Save a correction
- **GIVEN** a `total_mismatch` error
- **WHEN** the person changes the total to the right amount and saves
- **THEN** the request carries only the total, and the page shows the invoice without that finding and the new document status

#### Scenario: Nothing changed
- **WHEN** the person has not edited anything
- **THEN** save is disabled

#### Scenario: Invalid input
- **WHEN** the person types "abc" into an amount
- **THEN** the form shows an error at that field and sends nothing

#### Scenario: API rejects a value
- **WHEN** the API answers 422 naming the field `invoice_date`
- **THEN** the message appears at the date field and the typed values stay

#### Scenario: Document busy
- **WHEN** the API answers 409 `document_busy`
- **THEN** the page tells the person the document is still processing and keeps their edits

#### Scenario: History
- **THEN** the detail page lists the correction history (field, old value, new value, who, when)

### Requirement: Reprocess
The detail page SHALL offer a reprocess action for documents that are `FAILED`, `NEEDS_REVIEW` or `COMPLETED`, after confirmation, with the choice to rerun from the start or from extraction only. A document that is already `QUEUED` or `PROCESSING` SHALL NOT offer it. The page SHALL warn that re-extraction replaces manual corrections as the current version.

#### Scenario: Reprocess a failed document
- **GIVEN** a `FAILED` document
- **WHEN** the person confirms a reprocess
- **THEN** the request is sent, the page shows `QUEUED`, and follows the document until it finishes

#### Scenario: Busy document
- **GIVEN** a `PROCESSING` document
- **THEN** no reprocess action is offered

#### Scenario: Extraction not possible
- **WHEN** the API answers 409 `extraction_disabled` or `no_text`
- **THEN** the page explains why extraction cannot run

### Requirement: Review queue and failed documents
The review page SHALL list documents in `NEEDS_REVIEW` with their invoice summary and the number of findings, linking each to its detail page. It SHALL list `FAILED` documents with their error code, and offer a retry-all action that reports how many were queued and how many could not be.

#### Scenario: Queue contents
- **GIVEN** two `NEEDS_REVIEW` and one `FAILED` document
- **THEN** the review page shows the two in the queue and the failed one in the failed list

#### Scenario: Retry all
- **WHEN** the person confirms retry-all and the API reports two queued and none not queued
- **THEN** the page says "2 queued" and the list refreshes

#### Scenario: Empty queue
- **GIVEN** no document needs review
- **THEN** the page says nothing needs review
