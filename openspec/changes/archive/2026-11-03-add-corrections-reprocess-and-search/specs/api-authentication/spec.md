# Spec Delta

## Purpose

Protects the API with a shared secret so that only clients that know it can read or change documents, while keeping local development friction-free.

## ADDED Requirements

### Requirement: API key
When the `API_KEY` setting is configured, every request to a path under `/api/v1` SHALL carry the header `X-API-Key` with that exact value (compared in constant time); otherwise the response SHALL be 401 with detail `Invalid or missing API key`. The health endpoints and the generated API documentation SHALL stay open. The key SHALL NOT appear in logs.

#### Scenario: Correct key
- **GIVEN** `API_KEY` is set
- **WHEN** a client sends the matching `X-API-Key`
- **THEN** the request is handled normally

#### Scenario: Missing or wrong key
- **GIVEN** `API_KEY` is set
- **WHEN** a client sends no key, or a different key
- **THEN** the response is 401 and nothing is read or changed

#### Scenario: Health stays open
- **GIVEN** `API_KEY` is set
- **WHEN** a client requests `/healthz` without a key
- **THEN** the response is 200

#### Scenario: Browser preflight
- **GIVEN** `API_KEY` is set
- **WHEN** a browser sends a CORS preflight request without the key
- **THEN** it is answered by the CORS rules, not rejected as unauthorized

### Requirement: No key configured
When `API_KEY` is not configured, the API SHALL accept requests without a key and the system SHALL log a warning at startup that authentication is disabled.

#### Scenario: Local development
- **GIVEN** no `API_KEY`
- **WHEN** a client calls any endpoint without a key
- **THEN** the request is handled normally
