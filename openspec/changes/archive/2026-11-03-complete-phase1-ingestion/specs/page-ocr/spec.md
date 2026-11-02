# Spec Delta

## ADDED Requirements

### Requirement: Concurrent page reading
The OCR job SHALL read the pages of one document concurrently, at most the configured number of pages at the same time (`OCR_CONCURRENCY`, default 4, minimum 1), and SHALL save the same text, method and confidence for every page whatever the limit.

#### Scenario: Many pages
- **GIVEN** a document with 12 scanned pages and a limit of 4
- **WHEN** the OCR job runs
- **THEN** no more than 4 pages are being read at any moment
- **AND** all 12 pages are saved with method `ocr`

#### Scenario: Same result with a limit of 1
- **GIVEN** the same document and a limit of 1
- **WHEN** the OCR job runs
- **THEN** every page has the same text and confidence as with a limit of 4

#### Scenario: A failed read keeps earlier progress
- **GIVEN** a document where one page read raises an error after earlier batches were saved
- **WHEN** the OCR job runs
- **THEN** the error is raised so the retry policy applies
- **AND** the pages saved in earlier batches stay saved
