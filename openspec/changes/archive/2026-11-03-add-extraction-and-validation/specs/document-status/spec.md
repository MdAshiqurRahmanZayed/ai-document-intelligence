/# Spec Delta

## MODIFIED Requirements

### Requirement: Background processing records progress
The ingest job SHALL set the document to `PROCESSING` when it starts and SHALL record a processing event for each step with the stage, outcome, duration and attempt number. The document SHALL become `COMPLETED` when all of its pages have their text and, when extraction is enabled, extraction and validation have finished: at the end of the ingest job when no page needs OCR and extraction is not enabled, at the end of the OCR job when pages needed OCR and extraction is not enabled, and otherwise when the extraction job finishes, with the document staying `PROCESSING` in between. The extraction job SHALL set the document to `NEEDS_REVIEW` instead of `COMPLETED` when validation routes it for review.

#### Scenario: Successful run
- **WHEN** the ingest job runs for a queued document that needs no OCR and extraction is not enabled, and succeeds
- **THEN** the document status is `COMPLETED`
- **AND** the history contains a started event and a succeeded event for stage `ingest`, each with attempt 1

#### Scenario: Document waiting for OCR
- **WHEN** the ingest job succeeds for a document that has pages needing OCR
- **THEN** the history contains a succeeded event for stage `ingest`
- **AND** the document status is still `PROCESSING`
- **AND** the document becomes `COMPLETED` only after the OCR job succeeds when extraction is not enabled

#### Scenario: Document waiting for extraction
- **GIVEN** extraction is enabled and a document whose text is ready
- **WHEN** the ingest job (or the OCR job, for scanned pages) succeeds
- **THEN** the document status is still `PROCESSING`
- **AND** it becomes `COMPLETED` or `NEEDS_REVIEW` only when the extraction job finishes
- **AND** the history contains started and succeeded events for stage `extract`
