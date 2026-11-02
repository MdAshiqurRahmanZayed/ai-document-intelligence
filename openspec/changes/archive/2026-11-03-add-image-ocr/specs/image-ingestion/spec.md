# Spec Delta

## Purpose

Turns an uploaded image document (JPG, PNG or TIFF) into page records with stored page images, so the same OCR step that reads scanned PDF pages can read it, and fails clearly when the image cannot be read.

## ADDED Requirements

### Requirement: One page per image frame
When the ingest job runs for an image document, the system SHALL save one page record per frame, numbered from 1, with method `scanned` and no text, SHALL store each frame as a PNG at `pages/<document_id>/<page_no>.png` and record that key on the page, and SHALL set the document's page count.

#### Scenario: Single image
- **GIVEN** an uploaded JPG
- **WHEN** the ingest job runs
- **THEN** the document has one page record numbered 1 with method `scanned` and no text
- **AND** a PNG exists at `pages/<document_id>/1.png` and the page record references it
- **AND** the document's `page_count` is 1

#### Scenario: Multi-page TIFF
- **GIVEN** an uploaded TIFF with three frames
- **WHEN** the ingest job runs
- **THEN** the document has page records 1, 2 and 3, each with its own stored image
- **AND** the document's `page_count` is 3

### Requirement: Upright images of bounded size
The system SHALL apply the image's orientation metadata before storing a frame and SHALL scale a frame down, keeping its proportions, when its longest side exceeds the maximum image size, and SHALL NOT scale a smaller frame up.

#### Scenario: Rotated phone photo
- **GIVEN** a JPG whose orientation metadata says it is rotated by 90 degrees
- **WHEN** the ingest job runs
- **THEN** the stored page image is upright

#### Scenario: Oversized image
- **GIVEN** an image whose longest side is larger than the maximum image size
- **WHEN** the ingest job runs
- **THEN** the stored page image fits within the maximum size

### Requirement: Unreadable images fail with a clear code
If an image cannot be decoded, because it is truncated, damaged or far larger than can be processed safely, the system SHALL set the document to `FAILED` with error code `image_corrupt`, SHALL record a failed processing event, and SHALL NOT retry the job.

#### Scenario: Truncated image
- **GIVEN** an uploaded JPG whose data stops partway through
- **WHEN** the ingest job runs
- **THEN** the document is `FAILED` with error code `image_corrupt`
- **AND** no retry is scheduled

#### Scenario: Re-run of the same image
- **GIVEN** an image document whose page records already exist
- **WHEN** the ingest job runs again
- **THEN** each page record is updated in place and the document has exactly one record per page number
