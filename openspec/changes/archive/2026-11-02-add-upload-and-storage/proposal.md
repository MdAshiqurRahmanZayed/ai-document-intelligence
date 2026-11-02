# Proposal

## Why

The stack runs but cannot accept a document yet. Every later Phase 1 change (PDF extraction, OCR, spreadsheet parsing) needs the same entry point: files that arrive over the API are validated, stored safely, recorded in the database, and handed to a background job whose progress can be inspected. Building this first lets each extraction change plug into an existing, tested pipeline.

## What Changes

- **Upload API:** `POST /api/v1/documents` accepts several files in one multipart request and reports an outcome per file (accepted, duplicate, rejected with a reason). It returns `202 Accepted`.
- **Validation:** file type is decided from file contents (a small built-in signature table), not the filename; empty and oversized files are rejected; the size limit comes from `MAX_UPLOAD_MB`.
- **Duplicates:** a file with the same SHA-256 as an existing document returns that document and is not processed again.
- **Status API:** `GET /api/v1/documents/{id}` returns metadata, current status and processing history.
- **Object storage service:** a storage interface with an S3 implementation (SeaweedFS), streaming uploads and presigned URLs. Object keys use the document UUID and a type-derived extension, never the user's filename.
- **Database:** first Alembic migration enabling pgvector and creating `documents`, `pages` and `processing_events`, with async SQLAlchemy models.
- **Background job:** an `ingest` Celery task stub that moves a document `QUEUED → PROCESSING → COMPLETED`, records an event per step, retries with exponential backoff, and marks the document `FAILED` with an error code when retries run out.
- **Tests:** unit and API tests (empty, corrupt, oversized, wrong-type, duplicate files), run in Docker. A throwaway Postgres joins the `test` profile; CI gets a Postgres service.

**Out of scope:** reading text from PDFs, images or spreadsheets (next changes), extraction/validation/search tables, authentication and rate limiting, the frontend, a download endpoint for presigned URLs, and limits on the number of files per request.

## Capabilities

### New Capabilities
- `document-upload`: accepting multi-file uploads, validating type and size, rejecting bad files with reasons, and handling duplicate files.
- `document-status`: exposing a document's metadata, lifecycle status and processing history, including how background processing succeeds, retries and fails.

### Modified Capabilities
<!-- None: existing specs (service-health, runtime-configuration) keep their requirements. -->

## Impact

- **New code:** `backend/app/db/` (session, models), `backend/app/services/` (storage, documents), `backend/app/api/v1/documents.py`, `backend/app/workers/tasks.py`, first file in `backend/alembic/versions/`.
- **Changed code:** `backend/app/main.py` (router, session, enqueue wiring), `backend/alembic/env.py` (model metadata), `backend/pyproject.toml`.
- **New dependencies:** `python-multipart` (runtime), `openpyxl` (dev, for a spreadsheet test fixture).
- **Infra:** `docker-compose.yml` (Postgres for tests), `Makefile` (`make lint` skips the test database), `.github/workflows/ci.yml` (Postgres service).
- **API surface:** two new endpoints under `/api/v1`.
- **Data:** new tables; the existing database needs `alembic upgrade head` (`make migrate`).
