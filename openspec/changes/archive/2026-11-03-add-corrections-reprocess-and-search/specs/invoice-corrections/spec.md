# Spec Delta

## Purpose

Lets a person fix the values the system extracted from an invoice, keeps a record of every change, and checks the corrected invoice again so that documents leave review once their problems are fixed.

## ADDED Requirements

### Requirement: Correct an invoice
`PATCH /api/v1/documents/{id}/invoices/{invoice_index}` SHALL accept `fields` (an object) and an optional `edited_by` (free text, default `api`). The fields that can be changed are `invoice_number`, `invoice_date`, `supplier_name`, `customer_name`, `subtotal`, `tax`, `total`, `currency` and `line_items` (the whole list is replaced). A field set to `null` is cleared. The values SHALL be normalized exactly like extracted values (dates to ISO 8601, amounts to exact decimals, currency to an ISO 4217 code). The system SHALL save the result as a new version of the invoice and make it the current one, keep the earlier versions, and return the updated invoice in the same shape as the result endpoint.

#### Scenario: Fix a total
- **GIVEN** an invoice with total 130.00 and version 1
- **WHEN** a client patches `{"fields": {"total": "120.00"}}`
- **THEN** the response is 200 and the invoice has total 120.00 and version 2
- **AND** version 1 still exists and is no longer current

#### Scenario: Values are normalized
- **WHEN** a client patches `{"fields": {"invoice_date": "5 January 2026", "total": "1.234,50", "currency": "€"}}`
- **THEN** the stored values are `2026-01-05`, 1234.50 and `EUR`

#### Scenario: Clear a field
- **WHEN** a client patches `{"fields": {"customer_name": null}}`
- **THEN** the customer name of the new version is `null`

#### Scenario: Replace the line items
- **WHEN** a client patches `line_items` with two items
- **THEN** the new version has exactly those two items

#### Scenario: Unreadable value
- **WHEN** a client patches `{"fields": {"total": "lots"}}`
- **THEN** the response is 422 and names the field
- **AND** no new version is saved

#### Scenario: Unknown field
- **WHEN** a client patches a field that is not editable
- **THEN** the response is 422 and nothing is saved

#### Scenario: Nothing changes
- **WHEN** a client patches a value equal to the current one
- **THEN** the response is 200, no new version is saved and no correction is recorded

### Requirement: Audit trail
For every field whose value changes, the system SHALL record the invoice, the field, the old value, the new value, who edited it (`edited_by`) and when. `GET /api/v1/documents/{id}/corrections` SHALL return these records, newest first.

#### Scenario: Two fields changed
- **WHEN** a client changes the total and the currency in one request
- **THEN** two correction records exist, each with its old and new value and the editor
- **AND** the corrections endpoint lists them

#### Scenario: Unchanged fields are not recorded
- **WHEN** a request contains one changed and one unchanged field
- **THEN** only the changed field is recorded

### Requirement: Corrected values are trusted
A field that a person set SHALL have confidence 1 and no source quote in the new version; fields the person did not touch SHALL keep their confidence and source quote.

#### Scenario: Confidence after an edit
- **GIVEN** a supplier name with confidence 0.3
- **WHEN** a client corrects the supplier name
- **THEN** its confidence is 1 and the `low_confidence` warning for it is gone

### Requirement: Validation runs again
After a correction the system SHALL validate the corrected invoice again with the same rules, including the duplicate check against other documents, replacing the findings of that invoice, and SHALL set the document to `NEEDS_REVIEW` when any current finding of the document is an error or a low-confidence warning and to `COMPLETED` otherwise.

#### Scenario: The fix clears the review
- **GIVEN** a document in `NEEDS_REVIEW` whose only problem is a `total_mismatch`
- **WHEN** a client corrects the total so that subtotal plus tax equals it
- **THEN** the findings of the invoice no longer contain `total_mismatch`
- **AND** the document is `COMPLETED`

#### Scenario: The edit creates a problem
- **GIVEN** a `COMPLETED` document
- **WHEN** a client sets a total that does not match subtotal plus tax
- **THEN** the invoice has a `total_mismatch` error and the document is `NEEDS_REVIEW`

#### Scenario: Another invoice still has an error
- **GIVEN** a document with two invoices that each have an error
- **WHEN** a client fixes only one
- **THEN** the document stays `NEEDS_REVIEW`

### Requirement: Correction errors
The endpoint SHALL return 404 when the document or the invoice number does not exist, and 409 with reason `document_busy` while the document is `UPLOADED`, `QUEUED` or `PROCESSING`.

#### Scenario: Unknown invoice
- **WHEN** a client patches invoice 5 of a document that has two invoices
- **THEN** the response is 404

#### Scenario: Document still processing
- **WHEN** a client patches an invoice of a document that is `PROCESSING`
- **THEN** the response is 409 with reason `document_busy`
