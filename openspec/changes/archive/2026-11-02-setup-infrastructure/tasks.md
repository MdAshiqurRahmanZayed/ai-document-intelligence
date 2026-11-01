# Tasks

## 1. Repo foundation

- [x] 1.1 Fill `openspec/config.yaml` `context` (stack, constraints: Decimal money, no invented extraction values, tests never call real LLM, no secrets committed) and `rules` (proposal states out-of-scope; tasks include tests and a verification step) and verify `openspec validate setup-infrastructure` still passes
- [x] 1.2 Create `.env.example` listing every variable used in this change (app, Postgres, Redis, S3, CORS origin, host ports, readiness timeout, `MAX_UPLOAD_MB`, `GOOGLE_API_KEY` placeholder) with comments, and verify no real secret values are present
- [x] 1.3 Create `README.md` stub (overview, prerequisites, quickstart `cp .env.example .env && make up`, service URLs/ports, make targets) and `AI_DISCLOSURE.md` stub (tools used, how AI is used, review process), and verify the quickstart steps match the Makefile

## 2. Backend skeleton

- [x] 2.1 Initialise `backend/` with `uv` (`pyproject.toml`, Python 3.12, deps: fastapi, uvicorn[standard], pydantic-settings, structlog, sqlalchemy[asyncio], asyncpg, alembic, redis, celery, boto3; dev: pytest, pytest-asyncio, httpx, ruff, mypy, boto3-stubs) with ruff/mypy/pytest config, and verify `uv sync` and `uv run python -c "import fastapi"` succeed
- [x] 2.2 Implement `app/core/config.py` `Settings` (pydantic-settings, `SecretStr` for secrets, `.env` support, env overrides file) and add unit tests for: missing `DATABASE_URL` fails naming the field, invalid `MAX_UPLOAD_MB` fails, secrets masked in `repr`/dump, env var overrides `.env`; verify `uv run pytest tests/unit/test_config.py` passes
- [x] 2.3 Implement `app/core/logging.py` (structlog JSON renderer, stdlib + uvicorn loggers routed through it, request middleware with method/path/status/duration_ms/request_id) and add a test asserting a request produces a JSON log line with timestamp, level, service, message; verify test passes
- [x] 2.4 Implement `app/main.py` app factory (settings, logging, CORS for `WEB_ORIGIN`, router mounting, startup log of masked settings) and verify `uv run uvicorn app.main:app` starts and exits non-zero with a named-field error when `DATABASE_URL` is unset
- [x] 2.5 Initialise Alembic with async `env.py` reading `DATABASE_URL` from settings (no migrations yet) and verify `uv run alembic upgrade head` runs cleanly against a local Postgres
- [x] 2.6 Implement `app/workers/celery_app.py` (broker/backend from settings, JSON serializer, `acks_late`, queues `ingest`/`ocr`/`llm`/`embed` declared) with a `ping` task, and add a unit test running `ping` eagerly; verify test passes

## 3. Health endpoints

- [x] 3.1 Implement `GET /healthz` returning `{"status": "ok"}` with no dependency calls, and add tests for 200 response and 200 when dependencies are stubbed as failing; verify tests pass
- [x] 3.2 Implement readiness checks (database `SELECT 1`, Redis `PING`, S3 `head_bucket` in a thread) as injectable dependencies run concurrently with per-check timeout `READINESS_TIMEOUT_SECONDS` (default 2)
- [x] 3.3 Implement `GET /readyz` (200 + all `ok`, or 503 + per-check results; failure detail logged only) and add tests: all ok → 200; one failing → 503 with only that check `error`; hanging check → response within timeout + margin and `error`; failure body contains no exception text or DSN; verify all pass

## 4. Frontend skeleton

- [x] 4.1 Scaffold `frontend/` with `create-next-app` (App Router, TypeScript, Tailwind v4, ESLint, `src/`, npm), enable `output: "standalone"`, and verify `npm run build` succeeds
- [x] 4.2 Add `src/components/ui/StatusBadge.tsx` (pure Tailwind, ok/error/loading variants) and landing page that fetches `${NEXT_PUBLIC_API_URL}/readyz` and renders a badge per dependency plus overall status (handles API unreachable), and verify it renders in `npm run dev`
- [x] 4.3 Set up vitest + Testing Library + jsdom with a `StatusBadge` test covering all three variants, add `test` and `typecheck` npm scripts, and verify `npm test`, `npm run lint`, `npm run typecheck` pass

## 5. Containers and orchestration

- [x] 5.1 Write `backend/Dockerfile` (multi-stage, `uv sync --frozen --no-dev`, slim runtime, non-root user) and `backend/.dockerignore`, and verify `docker build backend` succeeds
- [x] 5.2 Write `frontend/Dockerfile` (multi-stage, Node 24, standalone output, non-root) and `frontend/.dockerignore`, and verify `docker build frontend` succeeds
- [x] 5.3 Write `docker-compose.yml`: `postgres` (pgvector/pgvector:pg16), `redis`, `storage` (SeaweedFS, pinned tag, S3 API, per design D16), `storage-init` (boto3, create bucket idempotently), `api`, `worker`, `web`; healthchecks per design D10; top-level `name: ai-document-intelligence`; one network `ai-document-intelligence-network` and volumes `ai-document-intelligence-postgres-data`/`-redis-data`/`-storage-data`, each with an explicit `name:` per design D15; host ports from `.env`; and verify `docker compose config` is valid and every network/volume name starts with `ai-document-intelligence-`
- [x] 5.4 Write `Makefile` targets `up`, `down`, `logs`, `migrate`, `test`, `lint`, `eval` (placeholder message until Phase 6), `help`, and verify each target runs (`make help` lists them)

## 6. CI

- [x] 6.1 Add `.github/workflows/ci.yml` with `backend` job (setup-uv, `uv sync`, ruff check, ruff format --check, mypy, pytest) and `frontend` job (Node 24, `npm ci`, lint, typecheck, vitest) on push and pull_request, and verify the same commands pass locally (`make lint && make test`)

## 7. Integration verification

- [x] 7.1 From a clean state (`make down -v`), run `cp .env.example .env && make up` and verify `docker compose ps` shows all long-running services healthy and `storage-init` exited 0, and that `docker network ls` and `docker volume ls` show only `ai-document-intelligence-`-prefixed resources for this stack (no `default` network, no unprefixed volumes)
- [x] 7.2 Verify `curl -i localhost:8000/healthz` → 200 and `curl -i localhost:8000/readyz` → 200 with `database`, `redis`, `storage` all `ok`
- [x] 7.3 Stop Redis (`docker compose stop redis`), verify `/readyz` → 503 with only `redis: error` and the web page shows Redis as failing, then restart Redis and verify recovery to 200
- [x] 7.4 Verify `http://localhost:3000` loads and shows all dependencies ok, and `docker compose exec worker celery -A app.workers.celery_app inspect ping` replies
- [x] 7.5 Verify `docker compose logs api` output is JSON lines with no secret values present (grep for the configured passwords/keys returns nothing)
- [x] 7.6 Run `openspec validate setup-infrastructure --strict` and verify it passes

## Workflow follow-up

- Update Phase 0 checkboxes in `~/Desktop/personal-project/ai-document-intelligence.md`.
- Archive the change with `/opsx:archive` after review.
- Rename branch `master` → `main` and create the first commit on `main` — requires user approval (protected branch).
- Push only when the user explicitly asks, after confirming remote, branch, and commits.
