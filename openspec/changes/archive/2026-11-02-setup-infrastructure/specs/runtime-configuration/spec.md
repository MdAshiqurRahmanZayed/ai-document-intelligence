# Spec Delta

## Purpose

Defines how the API and worker obtain configuration from the environment, so misconfiguration is caught at startup and secrets never leak into logs or responses.

## ADDED Requirements

### Requirement: Configuration from environment
The API and worker SHALL read all configuration (database, Redis, object storage, LLM key, limits) from environment variables, optionally loaded from a `.env` file, with no secret values hard-coded in source.

#### Scenario: Values supplied via environment
- **GIVEN** `DATABASE_URL` is set in the environment
- **WHEN** the API starts
- **THEN** it connects using that value

#### Scenario: Environment overrides .env file
- **GIVEN** a variable is set both in `.env` and in the process environment
- **WHEN** the service starts
- **THEN** the process environment value is used

### Requirement: Fail-fast validation
The API and worker SHALL validate configuration at startup and exit with a non-zero status and a message naming each missing or invalid variable, instead of starting in a broken state.

#### Scenario: Required variable missing
- **GIVEN** `DATABASE_URL` is not set
- **WHEN** the API starts
- **THEN** startup fails with a non-zero exit code
- **AND** the error output names `DATABASE_URL`

#### Scenario: Invalid value
- **GIVEN** `MAX_UPLOAD_MB` is set to `abc`
- **WHEN** the API starts
- **THEN** startup fails and the error output names `MAX_UPLOAD_MB` as invalid

### Requirement: Documented variables
Every configuration variable the services read SHALL be listed in `.env.example` with a safe placeholder or default and a short comment.

#### Scenario: Fresh local setup
- **WHEN** a developer copies `.env.example` to `.env` and fills in only the secrets
- **THEN** the full local stack starts successfully

### Requirement: Secrets never logged
Secret values (passwords, API keys, secret keys) SHALL NOT appear in logs, error messages, or HTTP responses, including when configuration is printed or validation fails.

#### Scenario: Settings logged at startup
- **WHEN** the service logs its effective configuration at startup
- **THEN** secret fields are shown masked (e.g. `**********`)

#### Scenario: Validation fails on a secret field
- **GIVEN** a secret variable has an invalid value
- **WHEN** startup validation fails
- **THEN** the error names the variable but does not print its value

### Requirement: Structured logs
The API and worker SHALL emit logs as one JSON object per line, each including at least timestamp, level, logger/service name, and message.

#### Scenario: Request handled
- **WHEN** the API handles any request
- **THEN** a JSON log line is emitted containing timestamp, level, service, and message
