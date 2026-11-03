# Tasks

## 1. Archive and test gap

- [x] 1.1 Archive `add-frontend-and-flower` with `/opsx:archive` (its tasks 1.4, 1.5 and 7.3 are the user's checks: tick them or accept archiving with them open) and sync its specs. Verify: `openspec validate --all --strict` passes and `openspec/specs/` contains `web-api-access`, `web-upload`, `web-document-review`, `web-search`, `worker-monitoring`.
- [x] 1.2 Add `frontend/src/components/PdfViewer.test.tsx`: mock `react-pdf` so `Document` calls `onPassword`, assert the "password-protected" message shows, that `window.prompt` is not called, and that the pages controls are absent. Verify: `cd frontend && npx vitest run src/components/PdfViewer.test.tsx` passes.

## 2. Facts first

- [x] 2.1 List the services, queues, ports and calls from `docker-compose.yml`, `backend/app/workers/` and `backend/app/api/v1/` into a scratch note (not committed). Verify: the diagram in 3.2 uses only items from this list.
- [x] 2.2 List every environment variable read by `backend/app/core/config.py`, `docker-compose.yml` and the web server routes. Verify: the list is used for 5.1 and 5.2.

## 3. README and diagram

- [x] 3.1 Rewrite `README.md`: what it does, quick start (`cp .env.example .env`, `make up`, `make migrate`, the sample command), where to open it, how to test (`make test`, `make check`, `make e2e`, which need a running stack), configuration, links to the docs, known limits. Verify: each command is run or checked against the Makefile; no stale text about the old frontend.
- [x] 3.2 Add one Mermaid architecture diagram to the README: browser, web server (proxy), API, Redis queues (`ingest`, `ocr`, `llm`, `embed`), workers, storage, PostgreSQL with pgvector, Gemini, Flower (optional). Verify: renders in GitHub's preview or a Mermaid checker, and matches task 2.1.
- [x] 3.3 In the README limits section, say the evaluation (dataset, report, `make eval`) was not done and why, and list other known limits (no user accounts, free-tier model quota, TIFF and spreadsheets have no preview, no per-page OCR progress). Verify: `make eval` text in the Makefile still says "not implemented" and the README agrees.

## 4. Security notes, AI disclosure, API docs check

- [x] 4.2 Write `docs/security.md`: API key and where it lives, the server-side proxy and its allow-list, file serving headers, prompt-injection guard, secrets and `.env`, limits (no user accounts, single shared key). Each measure names its file. Verify: every cited file path exists (`ls`).
- [x] 4.3 Write `docs/ai-disclosure.md` (at most one page): tools and model class used, areas helped (planning, code, tests, docs), how output was checked (tests, lint, manual runs, review), what remained the author's decisions. The author reviews and edits it, since it states their own practice. Verify: under one page, no claims the author disagrees with.
- [x] 4.4 Check `docs/api.md` and `docs/database-schema.md` against the code (routes, fields, error reasons, tables). Verify: `grep` each documented route in `backend/app/api/v1/`; fix any mismatch found.

## 5. Environment template and clean-clone check

- [x] 5.1 The user updates `.env.example` (the assistant cannot): add `FLOWER_USER`, `FLOWER_PASSWORD` (placeholder), `FLOWER_PORT`, `API_KEY` (empty, with the `openssl rand -hex 32` hint), set `GEMINI_EXTRACTION_MODEL=gemini-3.5-flash`, `GEMINI_FALLBACK_MODEL=gemini-3.8-flash`, keep `EMBEDDING_MODEL=models/gemini-embedding-001`, remove `NEXT_PUBLIC_API_URL`. Verify: the user pastes the file; compare with the list from 2.2.
- [x] 5.2 Compare the variable list from 2.2 with the pasted `.env.example`. Verify: none missing, none unused, no real secret values.
- [ ] 5.3 The user runs from a fresh clone: `cp .env.example .env`, `make up`, `make migrate`, `make check`, `make e2e`, then the quick start in the README. Verify: all pass; record the result (or each failure) for the PR description.

## 6. Finish

- [ ] 6.1 Run `openspec validate --all --strict`, `make check`, and read the README once as a stranger. Verify: all pass and nothing contradicts the code.
- [ ] 6.2 Commit atomically (`test(web)` for 1.2, `docs(repo)` for README and docs, `docs(openspec)` for the archive), no co-author trailers, branch `docs/repo-submission-docs`; push and open the PR only when the user asks. Verify: `git log --oneline` shows conventional messages.
