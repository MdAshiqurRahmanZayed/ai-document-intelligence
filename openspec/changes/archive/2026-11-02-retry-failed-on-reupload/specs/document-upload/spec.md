# Spec Delta

## MODIFIED Requirements

### Requirement: Duplicate detection
The API SHALL treat a file whose SHA-256 matches an existing document as a duplicate: return the existing document's id and not store or process it again. If that document is `FAILED`, the API SHALL instead clear its error, set it to `QUEUED`, queue a new job and report the file as `accepted` with the existing id.

#### Scenario: Same file uploaded twice
- **GIVEN** a PDF was accepted earlier as document A
- **WHEN** the same file is uploaded again, possibly under another filename
- **THEN** the result is `duplicate` with `document_id` equal to A
- **AND** no new document or stored object is created
- **AND** no new processing job is queued

#### Scenario: Same file twice in one request
- **WHEN** a client uploads identical bytes twice in one request
- **THEN** the first result is `accepted` and the second is `duplicate` with the same `document_id`

#### Scenario: Re-upload of a failed document
- **GIVEN** document A is `FAILED`
- **WHEN** the same file is uploaded again
- **THEN** the result is `accepted` with `document_id` equal to A
- **AND** A's status is `QUEUED` with no error code
- **AND** one new job is queued
- **AND** no new document or stored object is created

#### Scenario: Retry fails to queue
- **GIVEN** document A is `FAILED` and the queue refuses jobs
- **WHEN** the same file is uploaded again
- **THEN** the result is `rejected` with reason `queue_unavailable` and A's `document_id`
- **AND** A is `FAILED` with error code `queue_unavailable`

#### Scenario: Simultaneous re-uploads of a failed document
- **GIVEN** document A is `FAILED`
- **WHEN** two identical uploads arrive at the same time
- **THEN** exactly one is `accepted` and queues one job, and the other is `duplicate`
