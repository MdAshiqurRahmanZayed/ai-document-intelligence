# Spec Delta

## Purpose

Lets a client list and filter the documents that were processed and open the original file, so previously processed documents can be found again.

## ADDED Requirements

### Requirement: List documents
`GET /api/v1/documents` SHALL return documents newest first in pages of `limit` items (default 20, at most 100) with a `next_cursor` (null on the last page) that can be passed as `cursor` for the next page. Each item SHALL hold the document id, filename, status, source type, page count, error code, created and updated times, and a short summary of each current invoice (invoice index, number, supplier, date, total, currency).

#### Scenario: Pages
- **GIVEN** 25 documents and a limit of 10
- **WHEN** a client follows `next_cursor` until it is null
- **THEN** it receives 10, 10 and 5 documents, each once, newest first

#### Scenario: Invoice summary
- **WHEN** a client lists a document with two current invoices
- **THEN** the item shows both, in invoice order, with only their current versions

#### Scenario: Document without invoices
- **WHEN** a client lists a document that has no extraction
- **THEN** the item has an empty invoice list

#### Scenario: Bad parameters
- **WHEN** a client sends an unknown status, a limit above 100 or a malformed cursor
- **THEN** the response is 422

### Requirement: Filters
The list SHALL accept the filters `status`, `supplier` (case-insensitive part of the supplier name, ignoring punctuation and company forms), `invoice_number` (exact, ignoring case and punctuation), `date_from` and `date_to` (invoice date, inclusive), `amount_min` and `amount_max` (invoice total, inclusive) and `currency`. A document SHALL match when it has the given status and at least one current invoice that satisfies all the given invoice filters together.

#### Scenario: By status
- **WHEN** a client lists with `status=NEEDS_REVIEW`
- **THEN** only documents in that status are returned

#### Scenario: By supplier
- **GIVEN** an invoice from "Acme Industries Ltd."
- **WHEN** a client filters with `supplier=acme`
- **THEN** the document is returned

#### Scenario: By date and amount together
- **GIVEN** a document with one invoice dated 2026-01-05 for 50 and another dated 2026-03-01 for 500
- **WHEN** a client filters with `date_from=2026-02-01` and `amount_max=100`
- **THEN** the document is not returned, because no single invoice satisfies both

#### Scenario: By currency and amount range
- **WHEN** a client filters with `currency=EUR`, `amount_min=100` and `amount_max=200`
- **THEN** only documents with a EUR invoice whose total is between 100 and 200 are returned

### Requirement: Link to the original file
`GET /api/v1/documents/{id}/file` SHALL return a download link for the stored original that expires after 300 seconds, and 404 for an unknown document.

#### Scenario: Link
- **WHEN** a client requests the file link of a stored document
- **THEN** the response is 200 with a `url` and `expires_in` of 300

#### Scenario: Unknown document
- **WHEN** a client requests the file link of an id that does not exist
- **THEN** the response is 404
