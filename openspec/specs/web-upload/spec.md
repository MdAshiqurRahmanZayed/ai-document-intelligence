# web-upload Specification

## Purpose
Lets a person choose several documents at once, check them in the browser, send them to the API and see what happened to each file.

## Requirements

### Requirement: Choose several files
The upload page SHALL let a person add files by dragging them onto a drop area or by browsing, in several rounds, and SHALL list the chosen files with name and size before sending. A person SHALL be able to remove a file from the list before sending.

#### Scenario: Drop several files
- **WHEN** a person drops three files
- **THEN** all three appear in the list with their names and sizes

#### Scenario: Remove a file
- **GIVEN** three chosen files
- **WHEN** the person removes one
- **THEN** two remain and only those are sent

### Requirement: Check files before sending
The page SHALL refuse, with a reason shown next to the file, a file that is empty, larger than the API's per-file limit, or whose extension is not one of pdf, jpg, jpeg, png, tif, tiff, xlsx, xls, csv. Refused files SHALL NOT be sent. These checks are a convenience; the API remains the authority on the file type.

#### Scenario: Unsupported extension
- **WHEN** a person chooses `notes.docx`
- **THEN** it is listed as refused with the reason "unsupported type" and is not sent

#### Scenario: Too large
- **WHEN** a person chooses a file over the size limit
- **THEN** it is listed as refused with the reason "too large" and is not sent

#### Scenario: Valid files still sent
- **GIVEN** one refused and two valid files
- **WHEN** the person sends
- **THEN** only the two valid files are sent

### Requirement: Show a result for each file
After sending, the page SHALL show for each file whether it was accepted, was a duplicate of an earlier upload, or was rejected with the reason, and SHALL link accepted and duplicate files to their document page. A failure of the whole request SHALL be shown as an error with a way to send again.

#### Scenario: Mixed results
- **WHEN** the API accepts one file, reports one duplicate and rejects one as `empty_file`
- **THEN** the page shows "accepted" and "already uploaded" with links to their documents, and "rejected" with a readable reason

#### Scenario: Request fails
- **WHEN** the request fails before the API answers
- **THEN** the page shows an error and keeps the chosen files so they can be sent again

### Requirement: Show sending progress
While files are being sent the page SHALL show, for each file, a progress bar with the percentage of its bytes sent (0 to 100), and an overall percentage for the whole batch. A file SHALL show "sent, waiting for the server" once all its bytes are sent and until the API answers. The page SHALL prevent sending the same list twice at once.

#### Scenario: Percentages advance
- **GIVEN** a 10 MB file being sent
- **WHEN** 3 MB have been sent
- **THEN** its bar shows 30% and the overall bar reflects all files together

#### Scenario: Sent, not yet answered
- **WHEN** all bytes are sent and the API has not answered
- **THEN** the file shows 100% sent with the label "processing on server" and a spinner

#### Scenario: Done
- **WHEN** the API answers
- **THEN** the bar is replaced by the file's result (accepted, duplicate or rejected)

#### Scenario: Double submit
- **GIVEN** an upload in progress
- **WHEN** the person presses send again
- **THEN** no second request is made
