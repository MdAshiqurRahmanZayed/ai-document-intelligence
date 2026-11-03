# Monitoring workers with Flower

Flower is a web dashboard for the Celery workers. Use it to see whether the worker is alive, which queue a task is in, what it is doing now, and why it failed. It is off in a plain `make up`.

## Start it

1. Set a login in `.env` (see `.env.example`):

   ```
   FLOWER_USER=admin
   FLOWER_PASSWORD=<a long random value, e.g. from: openssl rand -hex 16>
   ```

2. Start the stack, then Flower:

   ```bash
   make up
   make flower        # prints http://localhost:5555
   ```

3. Open http://localhost:5555 and sign in. `docker compose --profile monitoring stop flower` stops it.

The service refuses to start without both variables and says which one is missing (`docker compose logs flower`).

| Variable | Default | Meaning |
|---|---|---|
| `FLOWER_USER`, `FLOWER_PASSWORD` | none (required) | Basic-auth login |
| `FLOWER_PORT` | `5555` | Host port; always published on `127.0.0.1` only |

## What to look at

| Page | Answers |
|---|---|
| **Workers** | Is the worker online? Which queues does it consume (`ingest`, `ocr`, `llm`, `embed`)? How many tasks are active, processed, failed? |
| **Tasks** | State of every task (received, started, succeeded, failed, retried), arguments, runtime, traceback. Filter by state or name. |
| **Broker** | Messages waiting per queue. A growing `ocr` or `llm` queue means the worker is behind or stuck. |

Typical checks:
- **Nothing happens after an upload:** Workers page shows the worker offline, or the Broker page shows messages waiting with no worker consuming that queue.
- **A document is `FAILED`:** open Tasks, filter `FAILURE`, read the traceback. The document's own history is in `GET /api/v1/documents/{id}` (`events`).
- **Slow OCR:** Tasks shows the runtime of each `ocr` task.

Task names are the Celery tasks in `backend/app/workers/tasks.py` (ingest, OCR, extract, embed).

## Limits

- Flower keeps task history **in memory** only. Restarting it, or a worker restart that drops events, clears the list. The durable record is the `processing_events` table, shown in the document's `events`.
- It shows tasks only while the worker runs with events enabled (`-E`, already set in `docker-compose.yml`).
- Task arguments (document ids, file names) are visible in the dashboard, which is why it is bound to localhost and needs a login. Do not expose the port.
