# Spec Delta

## Purpose

Reads the text of pages that have no embedded text: scanned PDF pages and image pages. Each page is cleaned up, read with OCR, and saved with its text and a confidence, in a job of its own so slow scans do not hold up other work.

## ADDED Requirements

### Requirement: OCR for scanned pages
When an ingest job leaves pages with method `scanned`, the system SHALL queue an OCR job for that document, and the OCR job SHALL read each such page's stored image, save the recognized text, set the method to `ocr`, and record the stage `ocr` in the processing history.

#### Scenario: Scanned image document
- **GIVEN** an image document whose page 1 is `scanned`
- **WHEN** the ingest job and then the OCR job run
- **THEN** page 1 has the recognized text and method `ocr`
- **AND** the history contains started and succeeded events for stage `ocr`

#### Scenario: Mixed PDF
- **GIVEN** a PDF with two text pages and one scanned page
- **WHEN** the ingest job and then the OCR job run
- **THEN** the text pages keep method `native` and their text unchanged
- **AND** only the scanned page is read with OCR and gets method `ocr`

#### Scenario: Nothing to read
- **GIVEN** a PDF whose pages all have embedded text
- **WHEN** the ingest job runs
- **THEN** no OCR job is queued

### Requirement: Page confidence
The system SHALL record for each OCR-read page a confidence between 0 and 1 equal to the mean of the OCR engine's confidence for the words it recognized, and SHALL record no confidence for a page with no recognized words.

#### Scenario: Clear text
- **GIVEN** a page image of clearly printed text
- **WHEN** the OCR job runs
- **THEN** the page confidence is between 0 and 1 and above 0.8

#### Scenario: Blank page
- **GIVEN** a scanned page that contains no text
- **WHEN** the OCR job runs
- **THEN** the page is saved with empty text, method `ocr` and no confidence
- **AND** the OCR job does not fail

### Requirement: Image clean-up before reading
The system SHALL convert each page image to grayscale, straighten a skewed page, reduce noise, and improve contrast before OCR, and SHALL NOT change the stored page image.

#### Scenario: Skewed scan
- **GIVEN** a page image of text rotated by a few degrees
- **WHEN** the OCR job runs
- **THEN** the recognized text matches the text of the unrotated page
- **AND** the stored image is unchanged

### Requirement: Safe to run again and in batches
The OCR job SHALL save results in batches during processing, SHALL read only pages still marked `scanned`, and SHALL be safe to run again for the same document.

#### Scenario: Re-run after partial progress
- **GIVEN** a document where some pages already have method `ocr` and others are still `scanned`
- **WHEN** the OCR job runs
- **THEN** only the remaining `scanned` pages are read
- **AND** the finished pages are not changed

#### Scenario: Re-ingest clears old OCR output
- **GIVEN** a PDF page previously read with OCR
- **WHEN** the ingest job runs again for the document and the page is still scanned
- **THEN** the page returns to method `scanned` with no text and no confidence

### Requirement: OCR failures are reported
If the OCR job fails, the system SHALL retry it with exponential backoff up to a fixed limit, and when retries are exhausted SHALL set the document to `FAILED` with error code `ocr_failed` and record a failed event for stage `ocr`.

#### Scenario: Engine error then success
- **GIVEN** the first OCR attempt raises an error and the second succeeds
- **WHEN** the OCR job runs
- **THEN** the document ends `COMPLETED`
- **AND** the history shows a failed attempt 1 and a succeeded attempt 2 for stage `ocr`

#### Scenario: Retries exhausted
- **GIVEN** every OCR attempt raises an error
- **WHEN** the retry limit is reached
- **THEN** the document status is `FAILED` with error code `ocr_failed`
