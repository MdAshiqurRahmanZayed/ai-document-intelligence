# Spec Delta

## Purpose

Lets a client run a document through the pipeline again, one document or all failed ones, without ever queueing the same document twice.

## ADDED Requirements

### Requirement: Reprocess a document
`POST /api/v1/documents/{id}/reprocess` with an optional `from_stage` of `ingest` (default) or `extract` SHALL set the document to `QUEUED`, clear its error code and message, queue the matching job and return 202 with the document id, its status and the stage. `ingest` runs the whole pipeline again; `extract` runs only extraction and validation on the pages already stored. Processing history, earlier invoice versions and corrections SHALL be kept.

#### Scenario: Retry a failed document
- **GIVEN** a document that is `FAILED` with an error code
- **WHEN** a client reprocesses it
- **THEN** the response is 202 and the document is `QUEUED` with no error code
- **AND** one ingest job is queued

#### Scenario: Re-run only extraction
- **GIVEN** a `NEEDS_REVIEW` document whose pages are stored and a configured Google API key
- **WHEN** a client reprocesses it with `from_stage` `extract`
- **THEN** one extraction job is queued and no ingest job

#### Scenario: Extraction needs text and a key
- **WHEN** a client asks for `extract` on a document without stored text, or when no Google API key is configured
- **THEN** the response is 409 with reason `no_text` or `extraction_disabled`, and the document is unchanged

#### Scenario: Re-extraction replaces corrections
- **GIVEN** a document with a manual correction
- **WHEN** it is reprocessed from `extract`
- **THEN** the new current version holds the model's values, and the corrected version and its audit records still exist

### Requirement: A document is queued at most once
Reprocessing SHALL be allowed for documents that are `FAILED`, `NEEDS_REVIEW` or `COMPLETED`, SHALL return 409 with reason `already_queued` for documents that are `UPLOADED`, `QUEUED` or `PROCESSING`, and SHALL queue exactly one job when several requests for the same document arrive together. If the broker refuses the job the document SHALL end `FAILED` with error code `queue_unavailable`, so it can be retried.

#### Scenario: Already running
- **WHEN** a client reprocesses a document that is `PROCESSING`
- **THEN** the response is 409 with reason `already_queued` and no job is queued

#### Scenario: Two requests at once
- **WHEN** two reprocess requests for the same failed document arrive together
- **THEN** exactly one job is queued and the other request gets 409

#### Scenario: Queue is down
- **GIVEN** the broker refuses the job
- **WHEN** a client reprocesses a document
- **THEN** the document is `FAILED` with error code `queue_unavailable`

#### Scenario: Unknown document
- **WHEN** a client reprocesses an id that does not exist
- **THEN** the response is 404

### Requirement: Retry all failed documents
`POST /api/v1/jobs/retry-failed` (optional `limit`, default 100) SHALL re-queue every document that is `FAILED`, oldest first, from the stage that failed (extraction for `extraction_failed`, the start for every other error code), and return the ids that were queued and the number that could not be.

#### Scenario: Several failures
- **GIVEN** one document failed in extraction and two failed in ingest
- **WHEN** a client retries all failed documents
- **THEN** three documents are `QUEUED`, one extraction job and two ingest jobs are queued, and the response lists the three ids

#### Scenario: Nothing failed
- **WHEN** no document is `FAILED`
- **THEN** the response is 200 with an empty list and no job is queued

#### Scenario: Limit
- **GIVEN** five failed documents and a limit of 2
- **WHEN** a client retries
- **THEN** the two oldest are queued and three stay `FAILED`
