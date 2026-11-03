# Proposal

## Why

The pipeline now turns uploads into validated invoices, but the assignment's Task 4 and Task 5 still ask for what makes that usable: manual corrections of extracted values, reprocessing of failed jobs, document search, and keyword filtering plus semantic search over stored data. Without them a reviewer can see that an invoice needs review (`NEEDS_REVIEW`) but cannot fix it, a failed document cannot be retried from the API, and processed documents cannot be found again. The frontend (next phase) needs all of these endpoints. Time is limited, so this one change delivers them with the least code that meets those requirements.

## What Changes

- **Corrections:** `PATCH /api/v1/documents/{id}/invoices/{invoice_index}` edits invoice fields (including line items). The edit is normalized like extracted values, saved as a new invoice version, recorded field by field in a new `corrections` table (who, old value, new value), and the invoice is validated again; the document leaves or enters `NEEDS_REVIEW` accordingly. `GET /api/v1/documents/{id}/corrections` returns the audit trail.
- **Reprocess:** `POST /api/v1/documents/{id}/reprocess` re-queues a document from the start or from extraction only; `POST /api/v1/jobs/retry-failed` re-queues every failed document from the stage that failed. Both are safe to repeat: a document is queued at most once.
- **Browsing:** `GET /api/v1/documents` lists documents, newest first, with cursor pagination and filters on status, supplier, invoice number, date range, amount range and currency; each item shows its invoices in short. `GET /api/v1/documents/{id}/file` returns a short-lived download link for the original file.
- **Indexing:** once a document's text is ready, it is split into overlapping chunks stored with a full-text vector; when a Google API key is set an `embed` job adds an embedding to each chunk. Embedding problems never fail a document.
- **Search:** `GET /api/v1/search` finds documents by keyword (PostgreSQL full-text), by meaning (pgvector, cosine) or both combined (reciprocal rank fusion), with the same filters as the list. Without a key, keyword search still works and hybrid falls back to it.
- **Authentication:** when `API_KEY` is set, every `/api/v1` request needs the `X-API-Key` header; without it the API stays open for local work.

Out of scope:
- The frontend, and the live progress stream (SSE): clients poll `GET /documents/{id}`.
- Rate limiting, user accounts and tokens: a single shared API key is enough for the assignment. Rate limiting moves to the hardening phase.
- Re-ranking, query expansion, per-field search ("supplier:acme"), and OCR-language settings.
- Re-extracting only some invoices of a document, and merging or splitting invoices by hand.
- Evaluation of search quality (evaluation phase).

## Capabilities

### New Capabilities
- `invoice-corrections`: manual edits with an audit trail and re-validation.
- `document-reprocessing`: re-queue a document, and bulk retry of failed documents.
- `document-browsing`: filtered, paginated document list and a download link for the original file.
- `document-search`: text indexing, embeddings, and keyword, semantic and hybrid search.
- `api-authentication`: a shared API key for the `/api/v1` API.

### Modified Capabilities

None. Existing behaviour is unchanged: with no API key and no Google key everything works as before, and the new tables and jobs are additive.

## Impact

- Code: new `app/services/` (`corrections.py`, `reprocess.py`, `listing.py`, `indexing.py`, `search.py`), `app/llm/embeddings.py`, `app/api/v1/` routes (corrections and file in `documents.py`, new `jobs.py`, `search.py`), `app/api/auth.py`, schemas, `workers/tasks.py` (index chunks when text is ready, new `embed_document` job), `app/main.py` (auth dependency, enqueue hook for re-extraction), `app/db/session.py` (pgvector codec).
- Database: one migration (`0003`) adding `corrections` and `chunks` (with a generated `tsv` column, a GIN index and an HNSW index).
- Dependencies: `pgvector` (SQLAlchemy type and asyncpg codec), `langchain-text-splitters`.
- Config: `API_KEY`, `EMBEDDING_MODEL` in `.env.example` (the embedding size is a fixed constant tied to the column).
- Docs: `docs/api.md`, `docs/database-schema.md`, the master plan.
