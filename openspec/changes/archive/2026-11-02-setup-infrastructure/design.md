# Design

## Context

Empty repository: only OpenSpec scaffolding, `.claude/`, `CLAUDE.md`, and `.gitignore` exist. Stack decisions are already fixed in `CLAUDE.md` (FastAPI, Celery + Redis, PostgreSQL + pgvector, S3-compatible object storage, Gemini via LangChain, Next.js + Tailwind v4). This change provides the runnable shell those decisions plug into. Requirements are in `specs/service-health` and `specs/runtime-configuration`; motivation in `proposal.md`.

Local tooling observed: Node 24, npm 11. Docker Desktop assumed available.

## Goals / Non-Goals

**Goals:**
- `cp .env.example .env && make up` brings up all six services healthy on a clean machine.
- Backend and frontend each have one passing test and green lint/typecheck, locally and in CI.
- Layout matches `CLAUDE.md` so later changes only add files, never move them.

**Non-Goals:**
- Database models, migrations with tables, upload or processing endpoints.
- Authentication, rate limiting (Phase 4).
- Production deployment (Kubernetes, TLS, reverse proxy).
- Python/Node dependency for LLM work (LangChain, Gemini) — added in Phase 2 when used.

## Decisions

**D1. Monorepo with `backend/` and `frontend/`, one root `docker-compose.yml`.**
One clone, one command. Alternative (two repos) adds overhead with no benefit for a single-team take-home.

**D2. `uv` for Python dependency management.**
Lockfile (`uv.lock`), fast installs in Docker and CI, PEP 621 `pyproject.toml`. Alternatives: Poetry (slower, own config format), pip-tools (more manual).

**D3. One backend image, two roles.**
`api` and `worker` services use the same `backend/Dockerfile`; only the command differs (`uvicorn` vs `celery worker`). Keeps code and dependency versions identical between them. Multi-stage build: `uv sync --frozen --no-dev` into a venv, copied into a slim runtime image running as a non-root user. System packages for OCR (Tesseract, libmagic) are deferred to Phase 1 to keep this image small until needed.

**D4. Settings via `pydantic-settings`, secrets typed as `SecretStr`.**
Gives fail-fast validation with field names in errors and masking by default (spec: runtime-configuration). Settings are built once at startup and injected as a FastAPI dependency so tests can override them. A small `app/core/config.py` holds the `Settings` class; worker imports the same class.

**D5. Logging via `structlog` → JSON renderer, stdlib logging routed through it.**
Uvicorn and Celery logs also come out as JSON lines. A request-logging middleware adds method, path, status, duration_ms, and request_id.

**D6. Readiness checks run concurrently with per-check timeout.**
`/readyz` runs `SELECT 1` (SQLAlchemy async engine + asyncpg), Redis `PING`, and S3 `head_bucket` concurrently via `asyncio.gather`, each wrapped in `asyncio.wait_for(timeout)`. Boto3 is sync, so the storage check runs in a thread (`asyncio.to_thread`). Exceptions are logged with detail and mapped to `"error"` in the response — no exception text in the body. Alternative: sequential checks — simpler, but worst-case latency is the sum of timeouts.

**D7. Health endpoints at root, not under `/api/v1`.**
`/healthz` and `/readyz` are infrastructure endpoints used by Docker healthchecks and probes; versioning them adds nothing. Business endpoints go under `/api/v1`.

**D8. Bucket created by a one-shot `storage-init` service.**
Runs a short `boto3` script (reusing the backend image, so no extra image to pull) that creates the bucket if `head_bucket` reports 404, then exits. API/worker `depends_on` it with `condition: service_completed_successfully`. Alternatives: an S3 CLI image (extra image, same result); creating the bucket from app code at startup — mixes infra provisioning into the app.

**D9. Postgres image `pgvector/pgvector:pg16`.**
Ships the extension; `CREATE EXTENSION vector` is run by the first Alembic migration (Phase 1), not here. Alembic is initialised now with an async `env.py` reading `DATABASE_URL` from settings, so `make migrate` works as a no-op.

**D10. Compose startup order via healthchecks.**
postgres (`pg_isready`), redis (`redis-cli ping`), storage (S3 port answers HTTP) → storage-init → api (Python `urllib` GET `/healthz`, since the slim image has no curl) and worker (`celery inspect ping`) → web (HTTP 200 on `/`). Volumes and network are explicitly named per D15.

**D11. Frontend scaffolded with `create-next-app` (App Router, TS, Tailwind v4, ESLint, `src/`), npm.**
Landing page is a client component that calls `GET {NEXT_PUBLIC_API_URL}/readyz` and shows each dependency as a status badge — a visible end-to-end check. API enables CORS for `WEB_ORIGIN` only. Dockerfile: multi-stage with `output: "standalone"`. Dev workflow outside Docker: `npm run dev`.

**D12. Testing baseline.**
Backend: pytest + httpx `ASGITransport`; readiness checks are injected dependencies so tests stub them (no live services needed for unit tests). Frontend: vitest + Testing Library + jsdom, one component test for the status badge. Real-dependency checks happen in the integration verification task via `make up`.

**D13. CI: GitHub Actions, two jobs (`backend`, `frontend`) on push and PR.**
Backend: `astral-sh/setup-uv`, `uv sync`, `ruff check`, `ruff format --check`, `mypy`, `pytest`. Frontend: `actions/setup-node` with npm cache, `npm ci`, `eslint`, `tsc --noEmit`, `vitest run`. No Docker build in CI yet (keeps CI fast; can be added later).

**D16. SeaweedFS as the S3-compatible object store (replaces MinIO).**
During apply, `minio/minio` and `minio/mc` on Docker Hub returned "pull access denied" and quay.io returned 401 for every tag. SeaweedFS (`chrislusf/seaweedfs`, Apache-2.0, actively maintained) runs as one container (`server -dir=/data -s3 -ip.bind=0.0.0.0`), takes its admin credentials from `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` (mapped from `S3_ACCESS_KEY`/`S3_SECRET_KEY`), and was verified with `boto3`: missing bucket → 404, create → ok, wrong credentials → 403. `-ip.bind=0.0.0.0` is required so the in-container healthcheck can reach `localhost`. Alternatives: RustFS (closest MinIO drop-in, but a young project) and the community MinIO binary in our own image (unmaintained builds, download may vanish). Trade-off: no MinIO-style web console; use the S3 API or SeaweedFS's master UI if needed.

**D14. Versions pinned.**
Python 3.12 (`requires-python = ">=3.12,<3.13"`), Node 24 LTS in Dockerfile and CI, Docker images pinned to a major/minor tag. Exact package versions locked by `uv.lock` and `package-lock.json`.

**D15. All Docker networks and volumes carry an explicit `ai-document-intelligence-` name.**
Compose top-level `name: ai-document-intelligence` sets the project name, and every network and volume also sets an explicit `name:` so it cannot collide with another project's resources on the same Docker host (generic names like `default`, `postgres_data` are shared-looking and easy to clash):
- Network: `ai-document-intelligence-network` (all services attached; no use of the implicit `default` network).
- Volumes: `ai-document-intelligence-postgres-data`, `ai-document-intelligence-redis-data`, `ai-document-intelligence-storage-data`.
Future volumes follow the same `ai-document-intelligence-<purpose>` pattern. Containers are left to Compose's project-prefixed defaults. Alternative: rely only on the Compose project name prefix — works, but breaks if someone runs with `-p` or `COMPOSE_PROJECT_NAME`, and explicit names also make `docker volume ls` / `docker network ls` self-describing. Trade-off: explicit names mean two checkouts of this repo on one host share volumes; acceptable (single local stack), and noted in README.

## Risks / Trade-offs

- [Storage image availability] → The official MinIO images (Docker Hub, quay.io) can no longer be pulled, so storage uses SeaweedFS (see D16). Storage is only reached through the S3 API and `S3_*` variables, so the server can be swapped again without code changes.
- [Port conflicts on a dev machine (5432, 6379, 3000, 8000)] → All host ports configurable in `.env`; defaults documented.
- [Apple Silicon vs amd64 image differences] → Use multi-arch official images only.
- [`/readyz` used as Docker healthcheck could flap during dependency restarts] → Docker healthcheck uses `/healthz`; `/readyz` is for operators and the UI.
- [Tailwind v4 / Next.js scaffold versions move fast] → Lock via `package-lock.json`; record versions in README.
- [Celery worker has no real tasks yet] → A `ping` task proves broker wiring; worker healthcheck uses `celery inspect ping`.

## Migration Plan

Greenfield — nothing to migrate. Rollback = `make down -v` (removes the `ai-document-intelligence-*` volumes and network; local data only, other projects' resources untouched).
