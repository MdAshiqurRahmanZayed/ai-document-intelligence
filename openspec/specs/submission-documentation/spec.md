# submission-documentation Specification

## Purpose
Defines the documents and setup a reviewer needs to run, understand and judge the system without asking the author, and requires the documents to say honestly what is and is not done.

## Requirements

### Requirement: README for a first-time reader
The README SHALL let a reader who has only Docker and `make` start the system, run its tests and find the documentation, and SHALL describe the design choices and known limits. Every command it shows SHALL work as written.

#### Scenario: Start from a clean clone
- **GIVEN** a fresh clone and Docker with Compose v2
- **WHEN** the reader follows the README quick start (`cp .env.example .env`, `make up`, `make migrate`)
- **THEN** the web interface opens at the documented address and its health indicator is green

#### Scenario: Run the tests
- **WHEN** the reader runs the commands in the README test section
- **THEN** they run to completion without extra setup, and the README says which need a running stack

#### Scenario: Limits stated
- **WHEN** the reader looks for what is not done
- **THEN** the README lists the known limits, including that the evaluation (dataset, report, `make eval`) was not done and why

### Requirement: Architecture diagram
The documentation SHALL include one diagram that shows the path from upload to search: web server, API, queues and workers, storage, database, and the model provider, with the direction of each call.

#### Scenario: Diagram matches the system
- **WHEN** the diagram is compared with `docker-compose.yml` and `docs/api.md`
- **THEN** every service and queue in it exists, and no running service that takes part in processing is missing

### Requirement: AI disclosure
The documentation SHALL state which parts of the work were produced with AI assistance, which tool and model class, and how the output was checked (tests, lint, manual runs).

#### Scenario: Disclosure present
- **WHEN** a reviewer opens the disclosure
- **THEN** it names the AI tools used, the areas they helped with, and the checks applied, in no more than one page

### Requirement: Security notes
The documentation SHALL summarise the security measures in the system and their limits: the API key and where it lives, the server-side proxy, how stored files are served, the treatment of document text as data for the model, secret handling, and what is not covered.

#### Scenario: Notes cover the key points
- **WHEN** a reviewer reads the notes
- **THEN** each measure names where it is implemented, and gaps (for example no user accounts) are stated

### Requirement: Complete environment template
`.env.example` SHALL document every variable the stack reads, with safe placeholder values and no real secrets, including the Flower variables, `API_KEY` and the model settings, and SHALL NOT list variables the code no longer reads.

#### Scenario: Template is complete
- **WHEN** the variables read by the API, worker, web server and compose file are compared with `.env.example`
- **THEN** each one appears there, and none listed there is unused

### Requirement: Verified from a clean clone
The submission SHALL have been checked from a fresh clone with `make up`, `make migrate`, `make check` and `make e2e`, and the result SHALL be recorded.

#### Scenario: Clean-clone run recorded
- **WHEN** the checks are run on a fresh clone with only `cp .env.example .env`
- **THEN** all pass, or each failure and its reason is recorded in the pull request description
