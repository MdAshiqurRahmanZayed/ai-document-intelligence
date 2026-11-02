# Spec Delta

## MODIFIED Requirements

### Requirement: Background processing records progress
The ingest job SHALL set the document to `PROCESSING` when it starts and SHALL record a processing event for each step with the stage, outcome, duration and attempt number. The document SHALL become `COMPLETED` when all of its pages have their text: at the end of the ingest job when no page needs OCR, otherwise when the OCR job finishes, with the document staying `PROCESSING` in between.

#### Scenario: Successful run
- **WHEN** the ingest job runs for a queued document that needs no OCR and succeeds
- **THEN** the document status is `COMPLETED`
- **AND** the history contains a started event and a succeeded event for stage `ingest`, each with attempt 1

#### Scenario: Document waiting for OCR
- **WHEN** the ingest job succeeds for a document that has pages needing OCR
- **THEN** the history contains a succeeded event for stage `ingest`
- **AND** the document status is still `PROCESSING`
- **AND** the document becomes `COMPLETED` only after the OCR job succeeds
