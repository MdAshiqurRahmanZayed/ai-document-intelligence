# Proposal

## Why

The repository has no runnable code yet. Every later phase (ingestion, OCR, LLM extraction, validation, search, UI, evaluation) needs the same foundation: a one-command local stack, a backend and worker that boot with validated configuration, a frontend shell, health signals that prove the dependencies are reachable, and CI that keeps quality gates green from the first commit. Building this first lets each later change focus on its own behavior instead of plumbing.

## What Changes

- Docker Compose stack with PostgreSQL 16 + pgvector, Redis, S3-compatible object storage (SeaweedFS, with automatic bucket creation), the FastAPI `api`, the Celery `worker`, and the Next.js `web` service; every service has a healthcheck. All networks and volumes use explicit `ai-document-intelligence-` names so they cannot overlap with other projects on the same Docker host.
- Backend skeleton (Python 3.12, `uv`): FastAPI app factory, environment-based settings with fail-fast validation, structured JSON logging, Alembic initialised against the database (no models yet), Celery app with a diagnostic ping task.
- Liveness (`/healthz`) and readiness (`/readyz`) endpoints; readiness reports database, Redis, and object-storage status individually.
- Frontend skeleton: Next.js (App Router) + TypeScript + Tailwind v4 with a landing page that shows backend readiness.
- `Makefile` targets: `up`, `down`, `logs`, `migrate`, `test`, `lint`, `eval` (placeholder until Phase 6).
- `.env.example` documenting every variable; no secrets committed.
- GitHub Actions CI: ruff, mypy, pytest (backend); eslint, tsc, vitest (frontend).
- Repo docs: `README.md` stub with quickstart, `AI_DISCLOSURE.md` stub.
- `openspec/config.yaml` filled with project context and artifact rules so later proposals inherit project constraints.

Out of scope: database models, upload endpoints, any document processing, auth, and capability specs for later phases.

## Capabilities

### New Capabilities
- `service-health`: liveness and readiness signals for the API, including per-dependency readiness for database, cache/broker, and object storage.
- `runtime-configuration`: how services load, validate, and protect configuration from the environment (fail-fast startup, documented variables, no secret leakage).

### Modified Capabilities
<!-- None: no existing specs. -->

## Impact

- New top-level files: `docker-compose.yml`, `Makefile`, `.env.example`, `README.md`, `AI_DISCLOSURE.md`, `.github/workflows/ci.yml`.
- New directories: `backend/` (app, tests, alembic, Dockerfile), `frontend/` (Next.js app, Dockerfile).
- `openspec/config.yaml` gains `context` and `rules`.
- New dependencies: FastAPI, uvicorn, pydantic-settings, structlog, SQLAlchemy (async) + asyncpg, Alembic, redis, celery, boto3, pytest/httpx/ruff/mypy; Next.js, React, Tailwind v4, vitest, Testing Library.
- Local ports: 8000 (api), 3000 (web), 5432 (postgres), 6379 (redis), 8333 (S3 API).
