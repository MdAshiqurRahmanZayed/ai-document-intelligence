# Spec Delta

## Purpose

Lets clients follow a document through background processing and understand what happened to it, including how failures and retries are reported.

## ADDED Requirements

### Requirement: Document details endpoint
The API SHALL expose `GET /api/v1/documents/{id}` returning the document's id, original filename, detected type, size, status, page count, error code and message (when failed), timestamps, and its processing history in chronological order.

#### Scenario: Existing document
- **WHEN** a client requests a document that was uploaded
- **THEN** the response status is 200
- **AND** the body contains `id`, `filename`, `mime`, `size`, `status`, `created_at` and an `events` list

#### Scenario: Unknown document
- **WHEN** a client requests an id that does not exist
- **THEN** the response status is 404

#### Scenario: Malformed id
- **WHEN** a client requests `/api/v1/documents/not-a-uuid`
- **THEN** the response status is 422

### Requirement: Document lifecycle
A document SHALL have exactly one status from `UPLOADED`, `QUEUED`, `PROCESSING`, `COMPLETED`, `NEEDS_REVIEW` and `FAILED`, and a newly accepted document SHALL move from `UPLOADED` to `QUEUED` once its processing job is handed to the queue.

#### Scenario: Accepted upload is queued
- **WHEN** a file is accepted
- **THEN** its status becomes `QUEUED`
- **AND** one ingest job is queued for it

### Requirement: Background processing records progress
The ingest job SHALL set the document to `PROCESSING` when it starts and to `COMPLETED` when it finishes, and SHALL record a processing event for each step with the stage, outcome, duration and attempt number.

#### Scenario: Successful run
- **WHEN** the ingest job runs for a queued document and succeeds
- **THEN** the document status is `COMPLETED`
- **AND** the history contains a started event and a succeeded event for stage `ingest`, each with attempt 1

### Requirement: Retries and failure reporting
The ingest job SHALL retry a failing attempt with exponential backoff up to a fixed limit, and when retries are exhausted SHALL set the document to `FAILED` with an error code and message and record a failed event.

#### Scenario: Transient failure then success
- **GIVEN** the first attempt raises an error and the second succeeds
- **WHEN** the job runs
- **THEN** the document ends `COMPLETED`
- **AND** the history shows the failed attempt 1 and the succeeded attempt 2

#### Scenario: Retries exhausted
- **GIVEN** every attempt raises an error
- **WHEN** the retry limit is reached
- **THEN** the document status is `FAILED`
- **AND** its `error_code` is `ingest_failed`
- **AND** the history contains a failed event for the final attempt

### Requirement: Job for a missing document
The ingest job SHALL NOT crash or retry forever when its document no longer exists.

#### Scenario: Document deleted before the job runs
- **WHEN** the ingest job runs for an id with no document record
- **THEN** the job ends without error and records nothing
