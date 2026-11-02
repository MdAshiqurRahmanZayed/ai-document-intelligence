# Proposal

## Why

Phase 1 turns every supported file into page text, but nothing reads it yet. The assignment's Task 2 asks for structured invoice data (number, date, supplier, customer, subtotal, tax, total, currency, line items) without invented values, Task 3 for validation, duplicate detection and manual-review flags, and the scenario for PDF to PDF and PDF to Excel cross-verification. Time is limited, so this one change delivers Phase 2 (extraction) and Phase 3 (validation and cross-verification) end to end with the least code that meets those requirements, so the system can be demonstrated from upload to a validated, cross-checked result.

## What Changes

- **Extraction:** once a document has its page text, a new job on the `llm` queue sends the text, in windows of pages, to a Gemini model through LangChain with structured output and returns every invoice found: invoice number, date, supplier, customer, subtotal, tax, total, currency and line items, plus a confidence and a source quote per field. Fields the document does not state stay `null`. Spreadsheet pages go through the same path, so Excel and CSV invoices need no separate column-mapping code.
- **Grounding and normalization:** a value that cannot be found in the page text is set to `null` and reported; dates become ISO 8601, amounts `Decimal`, currencies ISO 4217 codes.
- **Storage:** each invoice is saved as a versioned `extractions` row with the model and prompt version, with its key fields also stored as columns for lookups.
- **Validation:** rules flag missing required fields, bad numbers, line items that do not add up to the subtotal, subtotal plus tax that does not equal the total, implausible tax rates, dates in the future or very old, missing or unknown currency, and low-confidence fields. Findings are saved as `validation_errors` with a severity.
- **Duplicates:** the same supplier and invoice number in another document is an error; the same supplier, total and date with a different number is a warning.
- **Routing:** a document ends `COMPLETED`, or `NEEDS_REVIEW` when any validation error exists, a field has low confidence, or no invoice was found. Extraction failures end `FAILED` with `extraction_failed`.
- **Cross-verification:** compare two documents (PDF to PDF, PDF to Excel): invoices are matched by invoice number, falling back to supplier plus total plus date, and every field difference is reported and saved in `cross_checks`.
- **API:** `GET /api/v1/documents/{id}/result` returns the invoices with validation errors; `POST /api/v1/cross-verify` compares two documents.
- **Without an API key** extraction is skipped and documents complete as they do today, so the existing flows and tests are unchanged.

Out of scope:
- Corrections, reprocess and retry-failed endpoints, search and embeddings, API-key auth and rate limiting (the API completion phase).
- The frontend.
- A separate deterministic column-mapping step for spreadsheets and child documents for split invoices (the model reads spreadsheet text directly and returns every invoice; an invoice that spans two page windows can come back as two partial records, which validation flags for review).
- Vision (image) extraction and the vision OCR fallback.
- Currency conversion, tax-law checks and per-country invoice formats.
- Evaluation against a labelled dataset (the evaluation phase).

## Capabilities

### New Capabilities
- `invoice-extraction`: structured, grounded, normalized invoice data per document, stored with confidence and provenance, and returned by the result endpoint.
- `invoice-validation`: validation rules, duplicate detection and routing to `COMPLETED` or `NEEDS_REVIEW`.
- `cross-verification`: field-level comparison of the invoices of two documents.

### Modified Capabilities
- `document-status`: a document with extraction enabled stays `PROCESSING` after its text is ready and becomes `COMPLETED` or `NEEDS_REVIEW` when the extraction job finishes; extraction failures use `extraction_failed`.

## Impact

- Code: new `app/llm/` (extraction chain), `app/normalize/` (dates, amounts, currency), `app/validation/` (rules, duplicates), `app/pipeline/grounding.py`, `app/services/extraction.py`, `app/services/cross_verify.py`, `app/schemas/` (invoice and result models), `app/api/v1/` (result and cross-verify routes), `workers/tasks.py` (queue extraction after text, new task).
- Database: one migration adding `extractions`, `validation_errors` and `cross_checks`.
- Dependencies: `langchain-google-genai`, `langchain-core`, `rapidfuzz`, `dateparser`, `pycountry`.
- Prompts: new `backend/prompts/v1/extract_invoice.md`.
- Config: `GOOGLE_API_KEY` (already present), `GEMINI_EXTRACTION_MODEL`, `GEMINI_FALLBACK_MODEL`, `EXTRACTION_PAGES_PER_CALL`, `LOW_CONFIDENCE_THRESHOLD`, all in `.env.example`.
- Docs: `docs/api.md`, `docs/database-schema.md`, and the master plan.
