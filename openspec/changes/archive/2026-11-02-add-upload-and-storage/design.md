# Design

## Context

Phase 0 left a running stack: FastAPI app factory (`app/main.py`) that already owns an async SQLAlchemy engine for readiness, a Celery app with the four queues and `acks_late`, async Alembic with no migrations and `target_metadata = None`, a `storage-init` job that creates the bucket, and tests that run in Docker (`make test`). `app.state.checks` shows the established pattern for injectable collaborators that tests replace. See `proposal.md` for motivation and `specs/document-upload`, `specs/document-status` for requirements.

## Goals / Non-Goals

**Goals:**
- One tested path from HTTP upload to a stored object, a database row and a queued job.
- Business logic in `services/` with no FastAPI imports, so later pipeline code and workers reuse it.
- Failure behaviour that never leaves a half-created document.

**Non-Goals:**
- Parsing document content, extraction tables, auth, rate limits, per-request file-count limits, a download endpoint for presigned URLs.

## Decisions

**D1. Layout.** `app/db/` (base, models, session), `app/services/storage.py`, `app/services/documents.py` (upload and lookup logic), `app/schemas/documents.py` (Pydantic request/response), `app/api/v1/documents.py` (HTTP only), `app/workers/tasks.py`. Only `api/` imports FastAPI.

**D2. Async SQLAlchemy in the API, `asyncio.run` in the worker.** The API reuses the engine created in `create_app` (moved to `app.state.engine`) with a request-scoped session dependency. Celery tasks are synchronous, so each task runs one `asyncio.run(...)` with its own engine using `NullPool`. One async DB code path instead of adding a second sync driver. Alternative: psycopg for workers — a second driver and duplicated session code.

**D3. Schema.** UUID primary keys generated in Python. Status is a plain `String(20)` validated by a `StrEnum` in code, not a native Postgres enum (cheap to extend in later migrations). `sha256` is `CHAR(64)` with a unique constraint. Timestamps are `timestamptz` with `now()` defaults. `documents` also stores `source_type` (`pdf`, `image`, `spreadsheet`), derived from the detected type. `pages` has a unique `(document_id, page_no)` and cascading delete; `processing_events` is indexed on `(document_id, created_at)`. The migration runs `CREATE EXTENSION IF NOT EXISTS vector` (no vector columns yet) so later phases need no extension step. A `MetaData` naming convention keeps constraint names stable. The migration is generated with autogenerate against the test Postgres, then reviewed by hand.

**D4. Upload pipeline per file** (all in `services/documents.py`):
1. Read the stream in `CHUNK_SIZE` pieces (one constant, 8 MiB), updating SHA-256 and a byte counter; stop and reject as soon as the total passes `MAX_UPLOAD_MB`; reject zero bytes.
2. Detect the type from the first bytes (D5).
3. Look up the hash; if known, return `duplicate` with the existing id.
4. Rewind and upload to storage under `raw/{document_id}/original{ext}`.
5. Insert the row (`UPLOADED`) and commit. If the unique constraint on `sha256` fires (two identical files racing), delete the just-written object and return `duplicate`.
6. Set `QUEUED` and commit, then enqueue the ingest job (committing first stops a fast worker's `PROCESSING` from being overwritten). If enqueueing fails, set `FAILED` with error code `queue_unavailable` and report the file as `rejected` with that reason and its `document_id`; the document stays so a later reprocess endpoint (Phase 4) can re-queue it.

Storage failure in step 4 aborts before any row exists, which gives the "no record" guarantee. The batch endpoint returns `202` whenever the request is well-formed; outcomes are per file. Alternative: vary the status code by mix of outcomes — harder for clients and tests.

**D5. Content-based type detection with a small signature table, not `python-magic`.** Signatures: `%PDF-` (PDF), `FF D8 FF` (JPEG), `89 50 4E 47 0D 0A 1A 0A` (PNG), `II*\0` / `MM\0*` (TIFF). `PK\x03\x04` is only accepted as XLSX if the zip's entry list contains `xl/workbook.xml` (central directory read via `zipfile`, nothing is decompressed). The OLE signature `D0 CF 11 E0 A1 B1 1A E1` is accepted as XLS only when the filename ends in `.xls`, since OLE also wraps Word and others. CSV has no signature: it is accepted when the filename ends in `.csv` and the first chunk has no NUL bytes. The filename is used only for those two cases and never to override a binary signature. Alternative `python-magic` needs the `libmagic1` system package in both backend images and its answer for legacy XLS varies by libmagic version; the table is about 40 lines and fully deterministic.

**D6. Storage.** A `Storage` Protocol (`put`, `delete`, `presigned_url`) and `S3Storage` over boto3 with path-style addressing, a transfer config that uses the same `CHUNK_SIZE` for both the multipart threshold and part size (files up to 8 MiB go in one request, larger ones in 8 MiB parts), its own timeouts (connect 5 s, read 60 s, so uploads are not bound by the 2 s readiness timeout) and no automatic retries. boto3 is blocking, so calls run through `asyncio.to_thread`. Created in `create_app` as `app.state.storage`; tests use an in-memory implementation. `presigned_url` is implemented and unit-tested now but not exposed by an endpoint yet. Content type is stored as object metadata.

**D7. Enqueue is injectable.** `app.state.enqueue` defaults to `ingest_document.delay`; tests replace it with a recorder or a failing stub (same pattern as `app.state.checks`).

**D8. Ingest task.** `bind=True`, queue `ingest`, `autoretry_for=(Exception,)`, `retry_backoff=True`, `retry_backoff_max=60`, `retry_jitter=True`, `max_retries=3`. Each attempt writes a `started` event, sets `PROCESSING`, calls a single `run_pipeline(document)` function (a placeholder that later changes replace), sets `COMPLETED` and writes a `succeeded` event. An exception writes a `failed` event with the attempt number, then re-raises so Celery retries. A custom task base class implements `on_failure` (called once retries are exhausted) to set `FAILED`, `error_code="ingest_failed"` and the message. A missing document id returns quietly. `attempt` is `self.request.retries + 1`.

**D9. Test infrastructure.** A `postgres-test` service (`pgvector/pgvector:pg16`, data on `tmpfs`, healthcheck, on the app network, no published port) joins the `test` profile. `backend-test` depends on it and gets `TEST_DATABASE_URL`. A session fixture runs `alembic upgrade head` against it, so every API test also exercises the migration; a function fixture truncates tables between tests. `make lint` uses `--no-deps` so linting does not start Postgres. CI gets a Postgres service container and the same variable. DB-backed tests fail with a clear message when the variable is missing instead of skipping silently. Task tests call `task.apply()` (eager) against the test database; fake storage and a recording enqueue replace the real ones.

**D10. Dependencies.** Runtime: `python-multipart` (required by FastAPI for form uploads). Dev: `openpyxl` to build a real XLSX fixture. No Dockerfile change.

**D11. One chunk-size constant.** `CHUNK_SIZE = 8 * 1024 * 1024` lives in `app/services/storage.py` (imported by `documents.py`), so reading, hashing and S3 multipart parts always agree. It is a code constant, not a setting: the local environment is fixed and the value is not something to tune per deploy. `MAX_UPLOAD_MB` (default 100) stays the only size setting.

## Risks / Trade-offs

- [Starlette spools each upload to a temp file before our size check, so a huge request still uses disk] → Acceptable for this phase; request-size limits and rate limiting arrive with the API hardening in Phase 4.
- [No cap on files per request] → Same follow-up as above.
- [CSV and legacy XLS detection lean on the filename] → Restricted to those two types and combined with content checks (no NUL bytes; OLE signature). Wrongly named files fail later, cleanly, in the extraction changes.
- [A zip with `xl/workbook.xml` that is otherwise corrupt is accepted as XLSX] → Intended: type detection is shallow, the spreadsheet parser reports real corruption as `FAILED`.
- [`asyncio.run` per task creates an engine each time] → Negligible next to document processing; revisit if task volume makes it measurable.
- [Duplicate race between two concurrent uploads] → The unique constraint decides; the loser removes its object and reports `duplicate`.
- [Eager `task.apply()` may not reproduce retry timing] → Tests assert attempts, events and final status, not delays. If `apply()` does not re-run retries as expected, the test drives attempts explicitly.
- [Enqueue failure leaves a `FAILED` document] → Intended and visible; retry endpoint is planned in Phase 4. Until then, re-uploading the same bytes returns `duplicate` pointing at the failed document (seen in manual testing) and does not retry it.

## Migration Plan

Deploy, then run `make migrate` (`alembic upgrade head`). The migration is additive. Rollback: `alembic downgrade -1` drops the three tables and leaves the `vector` extension in place.
