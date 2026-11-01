# AI Document Intelligence

Upload invoices and receipts (PDF, scanned PDF, JPG/PNG/TIFF, XLSX/XLS, CSV), extract structured data with OCR and an LLM, validate it, review and correct it in a web UI, and search it.

> Work in progress. Runnable stack and setup instructions arrive with the `setup-infrastructure` change.

## Stack

FastAPI, Celery + Redis, PostgreSQL + pgvector, S3-compatible storage (SeaweedFS), Gemini via LangChain, Next.js + Tailwind. See [CLAUDE.md](CLAUDE.md) for conventions.

## Workflow

Spec-driven with [OpenSpec](https://github.com/Fission-AI/OpenSpec): specs and change proposals live in `openspec/`. Commits follow Conventional Commits (`.claude/skills/git-conventions/SKILL.md`).
