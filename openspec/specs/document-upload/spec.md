# document-upload Specification

## Purpose
Lets clients send business documents to the system in bulk and get a clear, per-file answer, while keeping unsafe, empty, oversized or already-known files out of processing.

## Requirements

### Requirement: Multi-file upload
The API SHALL accept one or more files in a single `POST /api/v1/documents` multipart request, respond `202 Accepted`, and report one result per file in request order.

#### Scenario: Two valid files
- **WHEN** a client uploads a PDF and a CSV in one request
- **THEN** the response status is 202
- **AND** the body lists two results, each with `status` `accepted` and a `document_id`

#### Scenario: Mixed outcomes
- **WHEN** a client uploads one valid PDF and one empty file
- **THEN** the PDF result is `accepted` with a `document_id`
- **AND** the empty file result is `rejected` with reason `empty_file`
- **AND** the valid file is still stored and queued

#### Scenario: No files
- **WHEN** a client sends the request without any file
- **THEN** the response status is 422

### Requirement: File type decided by content
The API SHALL accept only PDF, JPEG, PNG, TIFF, XLSX, XLS and CSV files, and SHALL decide the type from the file contents, not from the filename or the client-declared content type.

#### Scenario: Supported type
- **WHEN** a client uploads a file whose contents are a PNG image
- **THEN** the file is accepted and its stored type is `image/png`

#### Scenario: Renamed file
- **WHEN** a client uploads a ZIP archive named `invoice.pdf`
- **THEN** the result is `rejected` with reason `unsupported_type`

#### Scenario: Random bytes with a PDF name
- **WHEN** a client uploads corrupt bytes that are not a PDF, named `scan.pdf`
- **THEN** the result is `rejected` with reason `unsupported_type`

#### Scenario: CSV text
- **WHEN** a client uploads plain text with a `.csv` filename and no binary content
- **THEN** the file is accepted as `text/csv`

### Requirement: Size and emptiness limits
The API SHALL reject empty files and files larger than the configured `MAX_UPLOAD_MB`, without storing them.

#### Scenario: Empty file
- **WHEN** a client uploads a zero-byte file
- **THEN** the result is `rejected` with reason `empty_file`

#### Scenario: Oversized file
- **GIVEN** `MAX_UPLOAD_MB` is 1
- **WHEN** a client uploads a 2 MB file
- **THEN** the result is `rejected` with reason `file_too_large`
- **AND** nothing is stored for that file

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

### Requirement: Safe storage naming
The system SHALL store each uploaded file under a key derived from the document id and a file extension chosen from the detected type, and SHALL NOT use any part of the client-supplied filename in the key.

#### Scenario: Hostile filename
- **WHEN** a client uploads a valid PDF named `../../etc/passwd`
- **THEN** the object key contains only the document id and `.pdf`
- **AND** the original filename is kept only as metadata on the document record

### Requirement: Failed storage does not leave records
The system SHALL NOT leave a document record for a file that could not be written to object storage.

#### Scenario: Storage unavailable
- **GIVEN** object storage rejects the write
- **WHEN** a client uploads a valid file
- **THEN** the result is `rejected` with reason `storage_error`
- **AND** no document record exists for that file

### Requirement: Queue failure is reported
If an accepted file cannot be handed to the processing queue, the API SHALL keep the stored document, mark it `FAILED` with error code `queue_unavailable`, and report the file as `rejected` with that reason and its `document_id`.

#### Scenario: Queue unavailable
- **GIVEN** the processing queue refuses new jobs
- **WHEN** a client uploads a valid file
- **THEN** the result is `rejected` with reason `queue_unavailable` and a `document_id`
- **AND** the document's status is `FAILED` with error code `queue_unavailable`
