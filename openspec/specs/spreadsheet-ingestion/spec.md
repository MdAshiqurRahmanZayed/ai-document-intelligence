# spreadsheet-ingestion Specification

## Purpose

Turns an uploaded spreadsheet (XLSX, XLS or CSV) into page records with readable table text, so later stages can extract invoice data from it the same way as from PDFs and images, and fails clearly when the file cannot be read or holds no data.

## Requirements

### Requirement: Pages from every sheet
When the ingest job runs for a spreadsheet document, the system SHALL save the text of every sheet that holds data as page records numbered from 1 in sheet order, with method `native`, no stored image and no OCR confidence, SHALL set the document's page count, and SHALL complete the document without queueing an OCR job. Each page's text SHALL start with the sheet name.

#### Scenario: Multi-sheet workbook
- **GIVEN** an XLSX with three sheets, one of them empty
- **WHEN** the ingest job runs
- **THEN** the document has pages for the two sheets that hold data, in sheet order, each starting with its sheet name
- **AND** the document's `page_count` equals the number of saved pages
- **AND** the document status is `COMPLETED` and no OCR job was queued

#### Scenario: Legacy XLS
- **GIVEN** an XLS workbook with one sheet of data
- **WHEN** the ingest job runs
- **THEN** the document has one page containing that sheet's rows

#### Scenario: Re-run
- **GIVEN** a spreadsheet document that was already ingested
- **WHEN** the ingest job runs again
- **THEN** each page still exists exactly once with the same text

### Requirement: Readable table text
The text of a spreadsheet page SHALL list the header row first and then one line per data row, with cells separated by ` | `. The system SHALL skip rows and trailing columns that are completely empty, SHALL show the value of a merged cell in every cell it covers, SHALL write dates and date-times in ISO 8601, and SHALL write whole numbers without a decimal point and other numbers without floating-point noise (a stored 0.1 + 0.2 reads `0.3`).

#### Scenario: Empty rows and columns
- **GIVEN** a sheet with blank rows between records and blank columns at the right edge
- **WHEN** the sheet is read
- **THEN** the page text has no lines for the blank rows and no trailing empty cells

#### Scenario: Merged header cell
- **GIVEN** a header cell merged across two columns
- **WHEN** the sheet is read
- **THEN** both columns show the merged cell's value in the header line

#### Scenario: Dates and numbers
- **GIVEN** a date cell for 5 January 2026, a whole number 12 and a stored number 120.5
- **WHEN** the sheet is read
- **THEN** the text shows `2026-01-05`, `12` and `120.5`

### Requirement: Header row detection
The system SHALL treat the first row, within the first 20 non-empty rows, that has at least two filled cells all holding text as the header row, so title or address rows above the table are not mistaken for it. When no such row exists, the page text SHALL have no header line and the first row SHALL be treated as data.

#### Scenario: Title above the table
- **GIVEN** a sheet whose first row is a single company-name cell and whose second row holds the column names
- **WHEN** the sheet is read
- **THEN** the second row is the header and the company name appears above it as plain text

#### Scenario: No header
- **GIVEN** a sheet whose rows are all numbers
- **WHEN** the sheet is read
- **THEN** the page text has no header line and every row appears as data

### Requirement: Long sheets are split into pages
The system SHALL split a sheet with more than 100 data rows into several pages of at most 100 data rows each, SHALL repeat the sheet name and header on every page, and SHALL number the pages in order.

#### Scenario: 250-row sheet
- **GIVEN** a sheet with a header and 250 data rows
- **WHEN** the ingest job runs
- **THEN** three pages are saved holding 100, 100 and 50 data rows
- **AND** each page starts with the sheet name and the header line

### Requirement: CSV encoding and delimiter
For CSV files the system SHALL detect the text encoding (including UTF-8 with or without a byte-order mark and Latin-1) and the delimiter (`,`, `;`, tab or `|`), and SHALL treat the file as one sheet named after the document.

#### Scenario: Semicolon-separated Latin-1
- **GIVEN** a CSV encoded as Latin-1 that uses `;` as delimiter and contains an accented character
- **WHEN** the ingest job runs
- **THEN** the page text shows the cells split correctly and the accented character intact

#### Scenario: Quoted delimiter
- **GIVEN** a CSV cell holding `"Acme, Inc."`
- **WHEN** the ingest job runs
- **THEN** the text shows `Acme, Inc.` as one cell

### Requirement: Unreadable or empty spreadsheets fail with a clear code
If a spreadsheet cannot be opened, the system SHALL set the document to `FAILED` with error code `spreadsheet_corrupt`; if it opens but no sheet holds any data, with error code `spreadsheet_empty`. In both cases it SHALL record a failed processing event and SHALL NOT retry the job.

#### Scenario: Damaged workbook
- **GIVEN** an XLSX or XLS file that passed the upload type check but is damaged inside
- **WHEN** the ingest job runs
- **THEN** the document is `FAILED` with error code `spreadsheet_corrupt`
- **AND** the history shows a single attempt

#### Scenario: Workbook with no data
- **GIVEN** a workbook whose sheets are all empty, or a CSV that holds only blank lines
- **WHEN** the ingest job runs
- **THEN** the document is `FAILED` with error code `spreadsheet_empty`
- **AND** no page records exist for it
