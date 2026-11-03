# web-api-access Specification

## Purpose
Defines how the web interface reaches the API without exposing the API key to the browser, and how every screen reports loading, empty and failed states the same way.

## Requirements

### Requirement: Browser calls go through the web server
The web interface SHALL send every data request to its own origin. The web server SHALL forward it to the API, add the `X-API-Key` header from a server-side setting when one is configured, and return the API's status code and JSON body unchanged. The API key SHALL NOT appear in any file or response sent to the browser.

#### Scenario: Key added on the server
- **GIVEN** the web server has an API key configured
- **WHEN** the browser requests the document list
- **THEN** the API receives the request with `X-API-Key` and the browser receives the list

#### Scenario: Key never reaches the browser
- **WHEN** the built page bundles and every response sent to the browser are searched for the key
- **THEN** it is not found

#### Scenario: API errors are passed on
- **WHEN** the API answers 409 with `{"detail": {"reason": "document_busy"}}`
- **THEN** the browser receives status 409 with the same body

#### Scenario: API unreachable
- **WHEN** the API cannot be reached
- **THEN** the browser receives status 502 and the screen shows an error state, not a blank page

#### Scenario: No key configured
- **GIVEN** no API key is configured
- **WHEN** the browser sends a request
- **THEN** it is forwarded without an `X-API-Key` header

### Requirement: Original files are served through the web server
The web interface SHALL show and download a stored original from its own origin. The web server SHALL obtain the file through the API and stream it to the browser, honouring range requests, and SHALL mark it so the browser neither guesses its type nor lets it run scripts. A request for a document that does not exist SHALL answer 404.

#### Scenario: PDF shown
- **WHEN** the browser requests the original of a stored PDF
- **THEN** the file is streamed from the web server's origin with its content type

#### Scenario: Range request
- **WHEN** the browser asks for part of a file
- **THEN** only that part is returned with status 206

#### Scenario: Unknown or malformed id
- **WHEN** the id is not a valid document id or the document does not exist
- **THEN** the answer is 404 and nothing is fetched from storage

### Requirement: Loading, empty and error states
Every screen that loads data SHALL show a loading indicator while the request runs, an explanatory empty state when there is nothing to show, and an error message with a retry action when the request fails.

#### Scenario: Loading
- **WHEN** a screen has requested data and not yet received it
- **THEN** it shows a loading indicator

#### Scenario: Empty
- **WHEN** the API returns no documents or no search results
- **THEN** the screen says so and, for the document list, links to the upload page

#### Scenario: Failure with retry
- **WHEN** a request fails
- **THEN** the screen shows a readable message and a retry control that repeats the request

### Requirement: Readable API error messages
The web interface SHALL turn the API's error responses into short messages a person can act on and SHALL NOT show raw JSON, stack traces or internal reason codes alone.

#### Scenario: Known reason
- **WHEN** the API answers 409 with reason `document_busy`
- **THEN** the message says the document is still being processed and to try again shortly

#### Scenario: Unknown error
- **WHEN** the API answers with an error the interface has no message for
- **THEN** it shows a generic failure message with the status code
