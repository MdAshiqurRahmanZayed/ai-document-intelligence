# Spec Delta

## Purpose

Gives operators, container orchestration, and the frontend a reliable way to tell whether the API process is alive and whether it can reach the dependencies it needs to serve requests.

## ADDED Requirements

### Requirement: Liveness endpoint
The API SHALL expose `GET /healthz` that returns HTTP 200 with body `{"status": "ok"}` whenever the process can serve HTTP, without contacting any external dependency.

#### Scenario: Process is running
- **WHEN** a client sends `GET /healthz`
- **THEN** the response status is 200
- **AND** the body is `{"status": "ok"}`

#### Scenario: Dependency is down
- **GIVEN** the database is unreachable
- **WHEN** a client sends `GET /healthz`
- **THEN** the response status is still 200

### Requirement: Readiness endpoint
The API SHALL expose `GET /readyz` that checks the database, Redis, and object storage, and reports each check by name with status `ok` or `error`.

#### Scenario: All dependencies reachable
- **WHEN** a client sends `GET /readyz` and the database, Redis, and object storage bucket are all reachable
- **THEN** the response status is 200
- **AND** the body contains `"status": "ok"` and a `checks` object with `database`, `redis`, and `storage` each set to `ok`

#### Scenario: One dependency unreachable
- **GIVEN** Redis is unreachable
- **WHEN** a client sends `GET /readyz`
- **THEN** the response status is 503
- **AND** the body contains `"status": "error"` with `checks.redis` set to `error` and the other checks reporting their own result

#### Scenario: Storage bucket missing
- **GIVEN** object storage is reachable but the configured bucket does not exist
- **WHEN** a client sends `GET /readyz`
- **THEN** the response status is 503 with `checks.storage` set to `error`

### Requirement: Bounded readiness checks
Each readiness dependency check SHALL time out after a configured limit (default 2 seconds) so a hung dependency cannot hang the endpoint.

#### Scenario: Dependency hangs
- **GIVEN** a dependency accepts connections but never responds
- **WHEN** a client sends `GET /readyz`
- **THEN** the response arrives within the timeout plus a small margin
- **AND** that dependency's check is reported as `error`

### Requirement: Health responses expose no internals
Health responses SHALL NOT include connection strings, credentials, hostnames, or raw exception messages; failure details SHALL be written to server logs only.

#### Scenario: Database authentication fails
- **GIVEN** the database rejects the configured credentials
- **WHEN** a client sends `GET /readyz`
- **THEN** the response reports `checks.database` as `error` without any credential, DSN, or exception text
- **AND** the server log records the failure reason
