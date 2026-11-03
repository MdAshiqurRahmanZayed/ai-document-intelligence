# AI Document Intelligence

Upload invoices and receipts (PDF, scanned PDF, JPG/PNG/TIFF, XLSX/XLS, CSV), extract structured data with OCR and an LLM, validate it, review it in a web UI, and search it.

> The full journey runs in the browser: upload, processing progress, extracted values, validation, corrections, review queue and search. See [docs/frontend.md](docs/frontend.md) for the pages and a manual test guide.

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

To watch the worker and its tasks, run `make flower` (needs `FLOWER_USER` and `FLOWER_PASSWORD` in `.env`): [docs/monitoring.md](docs/monitoring.md).

## Check it works

```bash
docker compose ps -a                # 6 services healthy, storage-init Exited (0)
curl -i localhost:8000/healthz      # 200 {"status":"ok"}
curl -i localhost:8000/readyz       # 200, database / redis / storage all "ok"
```

Open http://localhost:3000: it opens the documents page, and the dot in the header is green when the API, database, redis and storage are all up (hover it for details).

Failure check:

```bash
docker compose stop redis
curl -i localhost:8000/readyz       # 503, only "redis": "error"; /healthz stays 200
docker compose start redis          # back to 200
```

## API

Run `make migrate` once (and after pulling new migrations) to create the tables. Endpoint reference: [docs/api.md](docs/api.md). Interactive docs: http://localhost:8000/docs

## Tests

Both run in throwaway Docker containers (`make test` also starts a temporary Postgres for the database tests and removes it afterwards), so you need no local Python or Node (except for `make e2e`, which runs Playwright on the host). They work while `make dev` or `make up` is running (use a second terminal) and never touch the running stack.

```bash
make test      # backend (pytest) + frontend (vitest)
make check     # lint, typecheck and all tests
make e2e       # browser journey against the running stack (make up first)
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
- The browser talks only to the web server (`/api/backend/...`), which forwards to the API and adds `API_KEY` on the server. Change `API_KEY` in `.env`, then `docker compose up -d api web worker`. See [docs/frontend.md](docs/frontend.md).

## Troubleshooting

| Problem | Fix |
|---|---|
| `.env not found` | Run `cp .env.example .env`. |
| `port is already allocated` | Change that port in `.env` (and in `DATABASE_URL` for Postgres), then `make up`. |
| `/readyz` returns 503 | Check which dependency says `error`; the reason is in `docker compose logs api`. |
| Start over | `docker compose down -v && make up` |
