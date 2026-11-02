# invoice-validation Specification

## Purpose

Checks every extracted invoice against business rules, detects duplicates across documents, records each finding with a severity, and routes documents that need a person to look at them to `NEEDS_REVIEW`.

## Requirements

### Requirement: Findings are recorded
The system SHALL save each validation finding with a code, the field it concerns (when it concerns one), a severity of `error` or `warning`, and a message, linked to the invoice (or only to the document for document-level findings). Running validation again for an invoice SHALL replace its earlier findings.

#### Scenario: Re-validation
- **GIVEN** an invoice with two saved findings
- **WHEN** validation runs again and finds one
- **THEN** only the one new finding is stored for the invoice

### Requirement: Required fields
The system SHALL record an error with code `missing_field` for each of invoice number, invoice date, supplier name and total that is `null`.

#### Scenario: Missing number and date
- **GIVEN** an invoice with no invoice number and no date
- **WHEN** validation runs
- **THEN** errors `missing_field` for `invoice_number` and `invoice_date` are recorded

### Requirement: Numeric validity
The system SHALL record an error `negative_amount` for any subtotal, tax, total, line quantity, unit price or line amount below zero, an error `implausible_amount` for any amount above 1 000 000 000 000, and a warning `line_amount_mismatch` when a line has quantity, unit price and amount and the amount differs from quantity times unit price by more than 0.02.

#### Scenario: Negative total
- **GIVEN** an invoice with total -50.00
- **WHEN** validation runs
- **THEN** an error `negative_amount` for `total` is recorded

#### Scenario: Line arithmetic
- **GIVEN** a line with quantity 3, unit price 10.00 and amount 35.00
- **WHEN** validation runs
- **THEN** a warning `line_amount_mismatch` is recorded for that line

### Requirement: Totals are consistent
When line items and a subtotal are present, the system SHALL record an error `line_items_sum_mismatch` if the sum of the line amounts differs from the subtotal by more than the tolerance (the larger of 0.02 and 0.5 percent of the subtotal). When subtotal, tax and total are all present, the system SHALL record an error `total_mismatch` if subtotal plus tax differs from the total by more than the same tolerance. The system SHALL record a warning `implausible_tax_rate` when tax divided by subtotal is below 0 or above 0.30.

#### Scenario: Line items do not add up
- **GIVEN** line amounts 40.00 and 50.00 and a subtotal of 100.00
- **WHEN** validation runs
- **THEN** an error `line_items_sum_mismatch` is recorded

#### Scenario: Total does not match
- **GIVEN** subtotal 100.00, tax 20.00 and total 130.00
- **WHEN** validation runs
- **THEN** an error `total_mismatch` is recorded

#### Scenario: Consistent invoice
- **GIVEN** line amounts 40.00 and 60.00, subtotal 100.00, tax 20.00 and total 120.00
- **WHEN** validation runs
- **THEN** none of these findings is recorded

#### Scenario: Missing parts
- **GIVEN** an invoice with a total but no subtotal and no tax
- **WHEN** validation runs
- **THEN** no totals-consistency finding is recorded

### Requirement: Dates and currency
The system SHALL record an error `future_date` when the invoice date is after today, a warning `old_date` when it is before 2000-01-01, a warning `missing_currency` when the currency is `null`, and an error `invalid_currency` when the currency is not an ISO 4217 code.

#### Scenario: Future date
- **GIVEN** an invoice dated one year from today
- **WHEN** validation runs
- **THEN** an error `future_date` is recorded

#### Scenario: Unknown currency
- **GIVEN** a currency "ZZZ"
- **WHEN** validation runs
- **THEN** an error `invalid_currency` is recorded

### Requirement: Low confidence
The system SHALL record a warning `low_confidence` for each non-null field whose confidence is below the threshold (`LOW_CONFIDENCE_THRESHOLD`, default 0.5).

#### Scenario: Uncertain field
- **GIVEN** a supplier name with confidence 0.3
- **WHEN** validation runs
- **THEN** a warning `low_confidence` for `supplier_name` is recorded

### Requirement: Duplicate invoices
The system SHALL record an error `duplicate_invoice` when another document has a current invoice with the same invoice number and the same normalized supplier name (ignoring case, punctuation and company-form suffixes such as Ltd, Inc, GmbH, AB), and a warning `possible_duplicate` when another document has a current invoice with the same normalized supplier, total and date but a different or missing number. Both findings SHALL name the other document.

#### Scenario: Same number and supplier
- **GIVEN** document A with invoice INV-7 from "Acme Ltd." and document B with invoice INV-7 from "ACME Ltd"
- **WHEN** validation runs for B
- **THEN** an error `duplicate_invoice` naming A is recorded for B's invoice

#### Scenario: Same amounts, different number
- **GIVEN** two documents with the same supplier, total and date but different invoice numbers
- **WHEN** validation runs for the second
- **THEN** a warning `possible_duplicate` naming the first is recorded

#### Scenario: Different supplier
- **GIVEN** two documents with the same invoice number and different suppliers
- **WHEN** validation runs
- **THEN** no duplicate finding is recorded

### Requirement: Routing for review
After extraction and validation the system SHALL set the document to `NEEDS_REVIEW` when any invoice has an error, when any `low_confidence` warning exists, or when no invoice was found (recorded as a document-level error `no_invoice_found`), and to `COMPLETED` otherwise.

#### Scenario: Clean invoice
- **GIVEN** an invoice with no errors and no low-confidence fields
- **WHEN** the extraction job finishes
- **THEN** the document is `COMPLETED`

#### Scenario: Invoice with an error
- **GIVEN** an invoice with a `total_mismatch` error
- **WHEN** the extraction job finishes
- **THEN** the document is `NEEDS_REVIEW`

#### Scenario: Warnings only
- **GIVEN** an invoice with only an `old_date` warning
- **WHEN** the extraction job finishes
- **THEN** the document is `COMPLETED`

#### Scenario: No invoice found
- **GIVEN** a document with no invoice
- **WHEN** the extraction job finishes
- **THEN** a document-level error `no_invoice_found` is recorded and the document is `NEEDS_REVIEW`
