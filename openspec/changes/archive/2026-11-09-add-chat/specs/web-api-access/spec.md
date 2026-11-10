# Spec Delta

## MODIFIED Requirements

### Requirement: Browser calls go through the web server
The web interface SHALL send every data request to its own origin. The web server SHALL forward it to the API, add the `X-API-Key` header from a server-side setting when one is configured, and return the API's status code and JSON body unchanged. The API key SHALL NOT appear in any file or response sent to the browser. The web server SHALL forward the `documents`, `search`, `jobs`, `cross-verify` and `chat` resources, and SHALL pass a `text/event-stream` response to the browser as it arrives, without holding it back until it ends.

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

#### Scenario: Chat is forwarded
- **WHEN** the browser posts a question to the chat resource
- **THEN** the API receives it with `X-API-Key` and the browser receives the answer events

#### Scenario: Stream is not buffered
- **WHEN** the API sends the first event of a stream and then waits
- **THEN** the browser receives that event before the stream ends
