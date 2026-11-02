# Tasks

## 1. Dependencies and test infrastructure

- [x] 1.1 Add `python-multipart` (runtime) and `openpyxl` (dev) to `backend/pyproject.toml`, refresh `uv.lock`, and verify `make test` still passes
- [x] 1.2 Add a `postgres-test` service (pgvector image, data on tmpfs, healthcheck, app network, no published port) to the `test` profile in `docker-compose.yml`, make `backend-test` depend on it and receive `TEST_DATABASE_URL`, and change `make lint` to run with `--no-deps`; verify `make test` starts it and `make lint` does not
- [x] 1.3 Add a Postgres service container and `TEST_DATABASE_URL` to the backend job in `.github/workflows/ci.yml`, and verify the file parses and the variable name matches `conftest.py`

## 2. Database

- [x] 2.1 Create `app/db/base.py` (declarative base with constraint naming convention), `app/db/models/` (`Document`, `Page`, `ProcessingEvent`, `DocumentStatus` StrEnum) and `app/db/session.py` (engine and session-maker helpers), and verify `mypy` is clean
- [x] 2.2 Point `alembic/env.py` at the models' metadata, autogenerate the first migration against the test Postgres, review it by hand (add `CREATE EXTENSION IF NOT EXISTS vector`), and verify `alembic upgrade head` then `downgrade -1` then `upgrade head` all succeed
- [x] 2.3 Add DB fixtures to `tests/conftest.py` (migrate once per session, truncate tables per test, fail with a clear message when `TEST_DATABASE_URL` is unset) and model tests for unique `sha256`, `(document_id, page_no)` uniqueness, cascade delete and default status; verify `make test` passes

## 3. Storage service

- [x] 3.1 Create `app/services/storage.py` with the `CHUNK_SIZE` constant (8 MiB), the `Storage` protocol, `S3Storage` (injected boto3 client and bucket, path-style, upload/delete/presigned URL) and an in-memory `FakeStorage` for tests, plus unit tests for put/delete calls, content type metadata, presigned URL generation and that the transfer config uses `CHUNK_SIZE`; verify they pass

## 4. Upload logic

- [x] 4.1 Create `app/services/filetypes.py` (signature table, XLSX check via zip entries, `.xls` and `.csv` rules from the design) and unit tests for PDF, JPEG, PNG, TIFF, real XLSX (built with openpyxl), OLE with and without `.xls`, CSV with and without NUL bytes, a ZIP named `.pdf`, random bytes named `.pdf`, and an empty input; verify they pass
- [x] 4.2 Create `app/services/documents.py` implementing the per-file upload pipeline from the design (hash and size limit read in `CHUNK_SIZE` pieces, type detection, duplicate lookup, storage write, insert, enqueue, `queue_unavailable` handling, duplicate race cleanup) with no FastAPI imports, and tests against the test database with `FakeStorage` and a recording enqueue for: accepted, a file spanning several chunks (hash matches a one-shot hash), empty, oversized, unsupported type, duplicate (sequential and same batch), unique-constraint race, storage error leaves no row or object, queue error leaves a `FAILED` document; verify they pass

## 5. API

- [x] 5.1 Create `app/schemas/documents.py` and `app/api/v1/documents.py` with `POST /api/v1/documents` (202, per-file results) and `GET /api/v1/documents/{id}` (details and events); wire engine, session, storage and enqueue into `create_app`; add httpx API tests for multi-file success, mixed outcomes, no files (422), hostile filename (key has only id and extension), unknown id (404), malformed id (422), and status `QUEUED` after accept; verify they pass
- [x] 5.2 Add the upload and status endpoints to the README (curl examples and the `make migrate` step), and verify each documented command runs as written against the running stack

## 6. Background job

- [x] 6.1 Create `app/workers/tasks.py` with the `ingest_document` task (queue `ingest`, retry with exponential backoff and jitter, `max_retries=3`, events per attempt, placeholder `run_pipeline`, `on_failure` setting `FAILED` with `ingest_failed`, quiet return for a missing document), register it with the Celery app, and add tests for success events and final status, failure then success, retries exhausted, and missing document; verify they pass

## 7. Integration verification

- [x] 7.1 Rebuild and start the stack (`make up`), run `make migrate`, and verify the three tables and the `vector` extension exist in Postgres
- [x] 7.2 Upload a real PDF, PNG, CSV and XLSX in one request with curl; verify four `accepted` results, objects present in the bucket under `raw/<id>/original.<ext>`, and each document reaching `COMPLETED` with started and succeeded events via `GET /api/v1/documents/{id}`
- [x] 7.3 Re-upload one of the files and verify `duplicate` with the same id and no new object; upload an empty file, a ZIP renamed `.pdf` and a file over `MAX_UPLOAD_MB` and verify each rejection reason
- [x] 7.4 Stop the worker, upload a file and verify status `QUEUED`; start the worker and verify it reaches `COMPLETED`; stop Redis, upload a file and verify `rejected` with `queue_unavailable` and a `FAILED` document; restore Redis
- [x] 7.5 Run `make lint` and `make test` (all earlier tests included) and `openspec validate add-upload-and-storage --strict`, and verify all pass

## Workflow follow-up

- Update the Phase 1 checkboxes and daily log in `~/Desktop/personal-project/ai-document-intelligence.md`.
- Archive the change with `/opsx:archive` after review, then commit in atomic commits on `feat/storage-add-upload-and-storage`.
- Push only when asked; open the PR into `main`.
