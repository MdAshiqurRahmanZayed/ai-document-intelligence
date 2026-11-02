# Design

## Context

Read from the code: `workers/tasks.py` has two jobs. The ingest job saves pages and either queues `ocr_document` (pages need OCR) or sets `COMPLETED`; the OCR job sets `COMPLETED`. Pages live in `pages` (`text`, `method`); spreadsheet pages hold the table as text (`Sheet: …`, header, rows separated by ` | `). Celery already declares the `llm` queue and the worker listens to it. `GOOGLE_API_KEY` is an optional setting; no LangChain package is installed. There is one Alembic migration (`0001`), no `llm/`, `validation/` or `normalize/` package, and `docs/database-schema.md` sketches the planned `extractions`, `validation_errors` and `cross_checks` tables. `services/`, `pipeline/`, `llm/`, `validation/` must not import FastAPI, money is `Decimal`, extraction never invents values, tests never call the real LLM. See `proposal.md` for motivation and `specs/` for requirements.

## Goals / Non-Goals

**Goals:**
- One model-driven extraction path for PDFs, images and spreadsheets, with grounding and normalization as plain, testable code.
- Validation and duplicate rules as pure functions of the extracted data.
- Existing flows and tests unchanged when no API key is set.
- The smallest set of tables, endpoints and files that makes upload to validated, cross-checked result demonstrable.

**Non-Goals:**
- Corrections, reprocess, search, auth (next phase), deterministic spreadsheet column mapping, child documents for split invoices, vision extraction (see proposal).

## Decisions

**D1. Extraction is a third job, queued by whichever step finishes the text.** `extraction_enabled` is `settings.google_api_key is not None`. At the end of the ingest job: pages need OCR → queue OCR (as today); else if enabled → queue `extract_document`; else `COMPLETED`. At the end of the OCR job: if enabled → queue `extract_document`, else `COMPLETED`. The document stays `PROCESSING` until the extraction job sets `COMPLETED` or `NEEDS_REVIEW`. The job runs on the `llm` queue with `rate_limit="30/m"` (provider quota guard until proper limiting), the same retry policy as the other jobs, its own `on_failure` setting `extraction_failed`, and stage `extract` events. Queueing happens after the commit, like OCR. Alternative: run extraction inside the ingest or OCR job. Rejected: a slow or rate-limited model call would hold the ingest queue and risk redelivery timeouts.

**D2. Layout (matches the project layout rules).**
- `app/schemas/invoice.py`: Pydantic models. `InvoiceDraft` (what the model returns) and `InvoiceData` (normalized, `Decimal`).
- `app/normalize/values.py`: `parse_amount`, `parse_date`, `normalize_currency`, `normalize_name`.
- `app/pipeline/grounding.py`: pure grounding check.
- `app/llm/extract.py`: prompt loading, chain, windows.
- `app/validation/rules.py` (pure rules and routing) and `app/validation/crosscheck.py` (pure matching and comparison).
- `app/services/extraction.py` (orchestration and DB), `app/services/cross_verify.py` (DB), `app/db/models/extraction.py` (`Extraction`, `ValidationIssue`, `CrossCheck`).
- `app/api/v1/`: the result route in `documents.py`, a new `cross_verify.py`.
Nothing under `services/`, `pipeline/`, `llm/`, `validation/` imports FastAPI.

**D3. The model returns strings, the code returns numbers.** `InvoiceDraft` holds every value as `str | None` (amounts, dates, currency) plus `line_items: list[LineItemDraft]` and `notes: list[FieldNote]` where a note is `{field, confidence, quote}`. Strings keep binary floats out of the pipeline, and a list of notes avoids free-form dictionaries, which Gemini's structured output handles poorly. `ExtractionResult` is `{invoices: list[InvoiceDraft]}`, so one call can return several invoices or none.

**D4. Chain: prompt, structured output, retry, fallback.** `ChatPromptTemplate` from `prompts/v1/extract_invoice.md` (system) and a human message that wraps the pages as `<document> … </document>`; `ChatGoogleGenerativeAI(model, temperature=0, timeout=90).with_structured_output(ExtractionResult, include_raw=True)`; `.with_retry(stop_after_attempt=2)`; `.with_fallbacks([same chain on the fallback model])`. `include_raw` exposes `usage_metadata`, which is logged with the model name and the page range. A parsing error is raised, so retry and fallback apply. Models are settings: `GEMINI_EXTRACTION_MODEL` (default `gemini-2.5-flash`) and `GEMINI_FALLBACK_MODEL` (default `gemini-2.5-pro`); the IDs are placeholders to verify (open question). `Extractor(chain)` takes the chain as a parameter, so tests pass a fake runnable. `GenericFakeChatModel` cannot back `with_structured_output`, so tests replace the chain, not the chat model, and check the prompt it receives.

**D5. Windows, not per-invoice segmentation.** Pages with text are sent in windows of `EXTRACTION_PAGES_PER_CALL` (default 6), each page labelled `[Page N]`. Windows are sequential, results are concatenated in order and numbered 0.. as `invoice_index`. A 1000-page document costs about 170 calls and is rate limited by D1. An invoice that straddles two windows comes back as two partial invoices; they usually fail the required-field and total rules, so they reach review. Alternative: detect invoice boundaries first and extract per segment (a second model pass and child documents): more code and cost for a case review already catches. Pages with empty text are skipped; a document with no text at all makes no model call and ends as "no invoice found".

**D6. Grounding runs on the window text, before normalization.** For each non-null scalar field the value is grounded when (a) the note's quote is found in the window text by `rapidfuzz.fuzz.partial_ratio(quote, text) >= 90` (case-insensitive), or (b) for amounts, the value parsed with `parse_amount` equals any amount parsed from the text (so "1,234.50" in the text grounds "1234.50"), or for text and dates, the raw value is found by the same fuzzy check. Failing fields are set to `null` with an `ungrounded_field` warning. Line items are grounded by their description and amount the same way, and an ungrounded line item is dropped with the warning. Alternative: only lower the confidence. Rejected: the assignment says never invent values, and a null is cheaper to review than a wrong number.

**D7. Normalization rules.** `parse_amount` strips currency symbols, spaces and a trailing currency code, reads parentheses as negative, and decides the decimal separator: when both `.` and `,` appear the last one is the decimal separator; with a single separator that appears once and is followed by exactly three digits it is a thousands separator (`1.234` is 1234); otherwise it is the decimal separator. The result is a `Decimal` quantized to 4 places at storage. `parse_date` uses `dateparser.parse` with day-first order for ambiguous numeric dates (ISO dates are unambiguous) and returns `YYYY-MM-DD`. `normalize_currency` maps `€ $ £` to `EUR USD GBP`, upper-cases three-letter codes, and keeps anything else as given for validation to flag. Ambiguous dates written `03/04/2026` can be wrong; the confidence note and review are the safety net (risk).

**D8. Tables (one migration, `0002`).**
- `extractions`: `id`, `document_id` (FK cascade), `invoice_index`, `version`, `is_current`, `data` (JSONB, normalized invoice with amounts as strings), `field_confidence` (JSONB), `grounding` (JSONB, field to quote), `model`, `prompt_version`, `created_at`, and denormalized lookup columns `invoice_number`, `supplier_norm`, `invoice_date`, `total` (`Numeric(18,4)`), `currency`. Unique `(document_id, invoice_index, version)`, index `(supplier_norm, invoice_number)`, index `(document_id, is_current)`.
- `validation_errors`: `id`, `document_id` (FK cascade), `extraction_id` (FK cascade, nullable for document-level findings), `code`, `field`, `severity`, `message`, `related_document_id` (nullable), `created_at`.
- `cross_checks`: `id`, `left_document_id` and `right_document_id` (FKs cascade), `left_extraction_id` and `right_extraction_id` (FKs `SET NULL`, nullable for unmatched), `match_key`, `status`, `diffs` (JSONB), `created_at`, index `(left_document_id, right_document_id)`.
The sketched `line_items` table is dropped: line items live in `data` (nothing queries them yet); the evaluation and search phases can add the table if needed. `corrections` and `chunks` belong to the next phase.

**D9. Validation is pure; duplicates need the database.** `rules.validate_invoice(data, confidence, today, threshold)` returns findings from the rules in the spec; tolerance is `max(0.02, 0.005 * subtotal)`. `rules.route(findings, has_invoices)` returns `NEEDS_REVIEW` or `COMPLETED`. Duplicate lookups run in `services/extraction.py` over the indexed columns: same `supplier_norm` and `invoice_number` in another document's current extraction gives an error; same `supplier_norm`, `total` and `invoice_date` with a different or missing number gives a warning. `normalize_name` casefolds, removes punctuation and drops trailing company-form words (ltd, limited, inc, llc, gmbh, ab, as, oy, plc, co, corp, sa, bv). Duplicates compare with other documents only, so a re-upload of the same file (already caught by the SHA-256) is not double reported.

**D10. Extraction job flow.** Load pages in order, build windows, call the extractor per window in `asyncio.to_thread` (LangChain's sync call), then ground, normalize, and in one transaction mark earlier versions not current and insert the new rows; then validate each invoice, replace its findings, add document-level `no_invoice_found` when needed, set the document status by `route`, and write the `extract` events. Re-running is safe: it only adds a version. A retry after a mid-job failure calls the model again (cost accepted; `max_retries=3`).

**D11. Cross-verification is a pure comparison over stored data.** `crosscheck.match(left, right)` pairs by normalized number (casefold, alphanumerics only), then by `supplier_norm` plus equal total, each right invoice used once, in left order; `compare(pair)` returns the differences for date, supplier (`normalize_name`), customer, subtotal, tax, total (0.01 tolerance), currency, line-item count and sum of line amounts. `services/cross_verify.py` loads the current extractions of both documents, replaces the stored `cross_checks` of the pair and returns the result. Alternative: cross-check automatically when a second document arrives. Rejected for now: matching rules and when to trigger are open product questions; the endpoint covers the assignment scenario.

**D12. API shapes.** `GET /api/v1/documents/{id}/result` returns `{document_id, status, invoices: [{extraction_id, invoice_index, version, data, field_confidence, grounding, model, prompt_version, validation_errors: [{code, field, severity, message, related_document_id}]}], document_errors: [...]}`. `POST /api/v1/cross-verify` takes `{left_document_id, right_document_id}` and returns `{checks: [{status, match_key, left, right, diffs: [{field, left, right}]}]}` with the error codes from the spec. `docs/api.md` is updated in the same task as each route.

**D13. Tests never call the real model.** The extractor's chain is injected: a fake runnable returns canned `ExtractionResult`s (and raises for the failure cases). Rules, normalization, grounding and cross-check functions are tested directly with parametrized cases; services and tasks use the real test database and a fake extractor; the prompt-injection scenario checks that the text reaches the model inside the delimiters.

## Risks / Trade-offs

- [Model errors or invented values] -> Null on missing, grounding check, per-field confidence, validation rules, and `NEEDS_REVIEW`; the evaluation phase measures accuracy.
- [An invoice split across two windows comes back as two partial records] -> Validation flags both (missing fields or totals); documented limitation.
- [Ambiguous dates (03/04/2026) and amounts (1.234) parsed the wrong way] -> Documented rules, confidence notes and review; no silent fix.
- [Free-tier quotas and 170 calls for a 1000-page document] -> `rate_limit` on the task, retry with backoff, windows are a setting; the paid tier is the answer for volume and for real financial data.
- [Free-tier terms let the provider use submitted data] -> Extraction is off without a key; the README (Phase 7) says to use the paid tier or Vertex for real data.
- [Retries repeat paid calls] -> At most 4 attempts per document; an `extraction_failed` document can be reprocessed later.
- [Duplicate rule false positives (same supplier, total and date, different invoices)] -> It is a warning, not an error, and does not route to review on its own.
- [Default model IDs may be retired] -> They are settings and a failing call surfaces as `extraction_failed` or falls back; verified at first real run.

## Migration Plan

Add the dependencies and the settings, run the migration (`make migrate`), rebuild the images (`make up`) so `prompts/` and the new packages are present, and set `GOOGLE_API_KEY` to turn extraction on. Without a key behaviour is unchanged. Documents processed earlier have text but no extractions; re-uploading is not possible for exact duplicates, so a shell call `extract_document.delay(<id>)` extracts them, and the reprocess endpoint arrives in the next phase. Rollback: revert the code and run `alembic downgrade 0001`; extraction data is derived and can be recomputed.

## Open Questions

- Which Gemini model IDs should be the defaults for extraction and fallback? Placeholders `gemini-2.5-flash` and `gemini-2.5-pro`; verified at the first real run, no spec change needed.
