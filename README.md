# AI Document Intelligence

Upload invoices and receipts (PDF, scanned PDF, JPG/PNG/TIFF, XLSX/XLS, CSV), extract structured data with OCR and an LLM, validate it, review it in a web UI, and search it.

> Phase 0: infrastructure only. The stack runs and reports its own health; document processing comes next.

## Run

Needs Docker with Compose v2 and `make`.

```bash
cp .env.example .env
make up        # background, waits until healthy
make dev       # or foreground with live logs (Ctrl+C stops)
make down      # stop, keeps data
```

| Service | URL |
|---|---|
| Web | http://localhost:3000 |
| API docs | http://localhost:8000/docs |
| Postgres (localhost only) | localhost:15432 |

Also running: `redis`, `worker` (Celery), `storage` (S3 API on 8333, bucket created by `storage-init`).

## Check it works

```bash
docker compose ps -a                # 6 services healthy, storage-init Exited (0)
curl -i localhost:8000/healthz      # 200 {"status":"ok"}
curl -i localhost:8000/readyz       # 200, database / redis / storage all "ok"
```

Open http://localhost:3000: four green badges (API, database, redis, storage).

Failure check:

```bash
docker compose stop redis
curl -i localhost:8000/readyz       # 503, only "redis": "error"; /healthz stays 200
docker compose start redis          # back to 200
```

## Tests

Both run in throwaway Docker containers, so you need no local Python or Node. They work while `make dev` or `make up` is running (use a second terminal) and never touch the running stack.

```bash
make test      # backend (pytest) + frontend (vitest): 13 + 3 passed
make lint      # ruff, mypy, eslint, tsc
```

Run one backend test file:

```bash
docker compose --profile test run --build --rm backend-test pytest tests/unit/test_health.py -v
```

## Configuration

- `.env.example` documents every variable. The API and worker refuse to start if one is missing or invalid, and name it.
- Secrets are masked in logs and never returned by any endpoint.
- Host ports are set in `.env` (`API_PORT`, `WEB_PORT`, `POSTGRES_PORT`, `REDIS_PORT`, `S3_PORT`).
- `NEXT_PUBLIC_API_URL` is baked into the web build; after changing it run `docker compose up -d --build web`.

## Troubleshooting

| Problem | Fix |
|---|---|
| `.env not found` | Run `cp .env.example .env`. |
| `port is already allocated` | Change that port in `.env` (and in `DATABASE_URL` for Postgres), then `make up`. |
| `/readyz` returns 503 | Check which dependency says `error`; the reason is in `docker compose logs api`. |
| Start over | `docker compose down -v && make up` |
