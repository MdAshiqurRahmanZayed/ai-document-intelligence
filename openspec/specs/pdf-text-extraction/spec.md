# pdf-text-extraction Specification

## Purpose
Turns a stored PDF into per-page records the rest of the pipeline can use: the text of each page, a clear marker for pages that need OCR, and a clear failure when the PDF cannot be read.

## Requirements

### Requirement: Per-page text
When the ingest job runs for a PDF document, the system SHALL save one page record per PDF page, numbered from 1, containing the page's embedded text and the method `native`, and SHALL set the document's page count.

#### Scenario: Digital PDF
- **GIVEN** an uploaded PDF with three pages that contain text
- **WHEN** the ingest job runs
- **THEN** the document has three page records numbered 1, 2 and 3, each with its page's text and method `native`
- **AND** the document's `page_count` is 3
- **AND** the document status is `COMPLETED`

#### Scenario: Text with NUL characters
- **GIVEN** a PDF page whose extracted text contains NUL characters
- **WHEN** the ingest job runs
- **THEN** the page is saved with the NUL characters removed

### Requirement: Scanned page detection
The system SHALL treat a page as scanned when its embedded text, ignoring whitespace, is shorter than 20 characters, and SHALL record such a page with method `scanned` and no text.

#### Scenario: Image-only page
- **GIVEN** a PDF whose second page is an image with no embedded text
- **WHEN** the ingest job runs
- **THEN** page 2 is recorded with method `scanned` and no text
- **AND** pages with text keep method `native`

### Requirement: Images for scanned pages only
The system SHALL render each scanned page to a PNG at 300 DPI, store it at `pages/<document_id>/<page_no>.png`, and record that key on the page record, and SHALL NOT render pages that have text.

#### Scenario: Mixed PDF
- **GIVEN** a PDF with two text pages and one scanned page
- **WHEN** the ingest job runs
- **THEN** exactly one image is stored, for the scanned page
- **AND** the scanned page record references that image key
- **AND** the text pages have no image key

#### Scenario: Oversized page
- **GIVEN** a PDF page whose 300 DPI rendering would exceed the maximum image size
- **WHEN** the page is rendered
- **THEN** the image is scaled down to fit the maximum size

### Requirement: Page records stored before images are referenced
The system SHALL store a scanned page's image before saving the page record that references it.

#### Scenario: Image upload fails
- **GIVEN** object storage rejects the image write for a scanned page
- **WHEN** the ingest job runs
- **THEN** no page record references a missing image
- **AND** the attempt fails and is retried under the normal retry policy

### Requirement: Large documents are processed incrementally
The system SHALL process pages one at a time, SHALL save page records in batches during processing, and SHALL be safe to run again for the same document.

#### Scenario: Thousand-page PDF
- **GIVEN** a PDF with 1000 text pages
- **WHEN** the ingest job runs
- **THEN** all 1000 page records exist and the document is `COMPLETED`
- **AND** memory use does not grow with the page count

#### Scenario: Re-run of the same document
- **GIVEN** a document whose page records already exist
- **WHEN** the ingest job runs again
- **THEN** each page record is updated in place
- **AND** the document has exactly one record per page number

### Requirement: Unusable PDFs fail with a clear code
If a PDF cannot be read, the system SHALL set the document to `FAILED` with error code `pdf_corrupt` when the file is damaged or has no pages (the PDF reader refuses a file without pages), `pdf_encrypted` when it needs a password, or `pdf_empty` when a file opens but reports zero pages, SHALL record a failed processing event, and SHALL NOT retry the job.

#### Scenario: Corrupt PDF
- **GIVEN** an uploaded file that starts like a PDF but is truncated
- **WHEN** the ingest job runs
- **THEN** the document is `FAILED` with error code `pdf_corrupt`
- **AND** no retry is scheduled

#### Scenario: Password-protected PDF
- **GIVEN** an uploaded PDF that requires a password
- **WHEN** the ingest job runs
- **THEN** the document is `FAILED` with error code `pdf_encrypted`

#### Scenario: PDF with no pages
- **GIVEN** an uploaded PDF that contains zero pages
- **WHEN** the ingest job runs
- **THEN** the document is `FAILED` with error code `pdf_corrupt`

### Requirement: Non-PDF documents are unaffected
The system SHALL NOT create page records for documents that are not PDFs in this change.

#### Scenario: CSV upload
- **GIVEN** an uploaded CSV document
- **WHEN** the ingest job runs
- **THEN** the document is `COMPLETED` with no page records
