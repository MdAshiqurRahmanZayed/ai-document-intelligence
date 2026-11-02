# AI Document Intelligence System

Processes invoices/receipts from PDF, scanned PDF, JPG/PNG/TIFF, XLSX/XLS, and CSV: text extraction + OCR → LLM structured extraction → validation → review UI + search.

## Stack
- **Backend:** Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2.0 (async) + Alembic
- **Jobs:** Celery + Redis (queues: `ingest`, `ocr`, `llm`, `embed`)
- **DB:** PostgreSQL 16 + pgvector (FTS via `tsvector`/GIN, vectors via HNSW)
- **Storage:** SeaweedFS (S3 API via `boto3`; any S3-compatible server works); DB stores only `storage_key`
- **Docs/OCR:** PyMuPDF, pdfplumber, pikepdf, Tesseract (`pytesseract`), OpenCV, Pillow
- **Spreadsheets:** pandas, openpyxl, xlrd, charset-normalizer
- **LLM:** Gemini via LangChain (`langchain-google-genai`), `with_structured_output(Pydantic)`, embeddings via `GoogleGenerativeAIEmbeddings`
- **Frontend:** Next.js (App Router) + TypeScript + Tailwind v4 — no shadcn; own components in `frontend/src/components/ui/`. TanStack Query, react-hook-form + zod.
- **Infra:** Docker Compose

## Layout
- `backend/app/` — `api/v1/` (HTTP only), `services/`, `pipeline/` (detect, pdf, ocr, preprocess, spreadsheet, segment), `llm/`, `validation/`, `normalize/`, `workers/`, `db/models/`, `schemas/`
- `backend/prompts/v1/` — versioned LLM prompts (files, not inline strings)
- `backend/tests/` — `unit/`, `integration/`, `api/`, `fixtures/`
- `frontend/` — Next.js app
- `eval/` — labeled dataset, `run_eval.py`, `results/report.md`
- `openspec/` — capability specs + change proposals
- `docs/` — architecture, DB schema, ADRs in `docs/decisions/`

## Conventions
- `services/`, `pipeline/`, `llm/`, `validation/` must not import FastAPI — testable without HTTP, callable from workers.
- Every pipeline stage idempotent; log to `processing_events` (stage, status, duration_ms, error).
- Money as `Decimal`, never float. Dates ISO 8601. Currency ISO 4217.
- Extraction never invents values: all fields optional, `null` when absent; keep field confidence + source grounding.
- Document text sent to the LLM is delimited and treated as data (prompt-injection guard).
- LangChain is a thin layer only (LLM, structured output, embeddings, vector store).
- Tests never call the real LLM — use fake chat models / recorded responses.
- Keep `docs/api.md` in sync whenever an endpoint, response field or error reason changes.
- Keep `docs/database-schema.md` in sync whenever a model or migration changes.
- Secrets only in `.env` (never committed); `.env.example` documents every variable.

## Commands (planned — update when Makefile exists)
- `make up` / `make down` — Docker Compose stack
- `make migrate` — Alembic upgrade
- `make test` — pytest + vitest
- `make lint` — ruff + mypy, eslint + tsc
- `make eval` — run evaluation, write `eval/results/`

## Workflow
- Spec-driven with OpenSpec: `/opsx:propose` → review → `/opsx:apply` → verify (lint) → tests → API review → `/opsx:archive` → commit.
- Feature work on `<type>/<scope>-<slug>` branches.

## Git
- Follow `.claude/skills/git-conventions/SKILL.md` for commits, branches, PRs.
- Never push by default; push only on explicit request, after confirming remote/branch/commits.
- Protected branches `main`, `development`, `production`: ask before committing directly, merging into, rebasing, or cherry-picking onto them.
