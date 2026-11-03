# Spec Delta

## Purpose

Lets a developer see whether the background workers are running and what tasks they handle, so a stuck or failing pipeline can be investigated without reading container logs.

## ADDED Requirements

### Requirement: Flower dashboard
The stack SHALL offer a Flower dashboard that shows the workers that are online, the queues they consume (`ingest`, `ocr`, `llm`, `embed`) and the state of tasks (received, started, succeeded, failed, retried) with their arguments, runtime and error. It SHALL be started only when the `monitoring` Compose profile is enabled, so the default stack is unchanged.

#### Scenario: Default stack
- **WHEN** the stack is started without the `monitoring` profile
- **THEN** no Flower service runs

#### Scenario: Monitoring on
- **WHEN** the stack is started with the `monitoring` profile
- **THEN** the dashboard is reachable on the Flower port of the host and lists the worker as online

#### Scenario: Task visible
- **GIVEN** monitoring is on
- **WHEN** a document is uploaded
- **THEN** its ingest task appears in the dashboard with its state and runtime

### Requirement: Task events from workers
The worker SHALL send task events so that task states reach the dashboard.

#### Scenario: Events on
- **WHEN** a worker starts
- **THEN** it publishes task events

### Requirement: Dashboard access is restricted
The dashboard SHALL be published only on the host's loopback address and SHALL require basic authentication using credentials from the environment. It SHALL NOT start without credentials set.

#### Scenario: Loopback only
- **WHEN** the dashboard port is inspected on the host
- **THEN** it is bound to 127.0.0.1 only

#### Scenario: Login required
- **WHEN** a request to the dashboard carries no or wrong credentials
- **THEN** it is refused with 401

#### Scenario: No credentials configured
- **GIVEN** the monitoring profile is enabled and the credentials are not set
- **THEN** the service fails to start with a message naming the missing variable

### Requirement: Shortcut and documentation
There SHALL be a `make flower` target that starts the dashboard, and the documentation SHALL state its address, the variables that configure it and what it can and cannot show.

#### Scenario: Make target
- **WHEN** a developer runs `make flower`
- **THEN** the stack plus the dashboard are running and the address is printed
