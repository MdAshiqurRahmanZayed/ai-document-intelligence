# Spec Delta

## Purpose

Compares the invoices extracted from two documents, for example a PDF against an Excel export or two PDFs, so that differences between sources are found and reported field by field.

## ADDED Requirements

### Requirement: Matching invoices between documents
`POST /api/v1/cross-verify` with a left and a right document id SHALL match each current invoice of the left document to at most one current invoice of the right document, first by equal normalized invoice number, otherwise by equal normalized supplier and equal total, and SHALL report the invoices that have no match as unmatched, on the side they come from.

#### Scenario: Matched by number
- **GIVEN** both documents contain invoice INV-7
- **WHEN** a client cross-verifies them
- **THEN** the two INV-7 invoices are compared with each other

#### Scenario: Matched by supplier and total
- **GIVEN** the left invoice has no number and the right invoice has number INV-9, with the same supplier and total
- **WHEN** a client cross-verifies the documents
- **THEN** the two invoices are compared with each other

#### Scenario: Unmatched invoices
- **GIVEN** the right document has an invoice the left does not
- **WHEN** a client cross-verifies the documents
- **THEN** the response lists it as unmatched on the right side

### Requirement: Field differences
For each matched pair the system SHALL compare invoice date, supplier (normalized), customer (normalized), subtotal, tax, total, currency, the number of line items and the sum of the line amounts, treating amounts that differ by 0.01 or less as equal, and SHALL report every difference with the field, the left value and the right value. A pair with no difference SHALL have the status `match` and a pair with any difference the status `mismatch`.

#### Scenario: Equal invoices
- **GIVEN** a PDF and an Excel file stating the same invoice
- **WHEN** a client cross-verifies them
- **THEN** the pair has status `match` and no differences

#### Scenario: Different total
- **GIVEN** the PDF states a total of 120.00 and the Excel file 125.00
- **WHEN** a client cross-verifies them
- **THEN** the pair has status `mismatch` with a difference for `total` showing 120.00 and 125.00

#### Scenario: Rounding only
- **GIVEN** totals 120.00 and 120.01
- **WHEN** a client cross-verifies the documents
- **THEN** the totals are not reported as different

### Requirement: Results are stored
The system SHALL save each cross-check (matched pair or unmatched invoice) with its status and differences, and SHALL replace the earlier results for the same pair of documents when the comparison is run again.

#### Scenario: Run twice
- **GIVEN** a pair of documents that was cross-verified before
- **WHEN** a client cross-verifies the same pair again
- **THEN** only the results of the latest run are stored for the pair

### Requirement: Errors
The endpoint SHALL return 404 when either document does not exist, 422 when both ids are the same document, and 409 with reason `not_extracted` when either document has no current invoices.

#### Scenario: Unknown document
- **WHEN** a client cross-verifies a document that does not exist
- **THEN** the response status is 404

#### Scenario: Same document twice
- **WHEN** a client sends the same id on both sides
- **THEN** the response status is 422

#### Scenario: Nothing extracted
- **GIVEN** a document with no current invoices
- **WHEN** a client cross-verifies it with another document
- **THEN** the response status is 409 with reason `not_extracted`
