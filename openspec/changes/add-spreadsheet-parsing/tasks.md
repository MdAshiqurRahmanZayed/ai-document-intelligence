# Tasks

## 1. Dependencies and test samples

- [ ] 1.1 Add `xlrd` and `charset-normalizer` to `backend/pyproject.toml` runtime dependencies and `xlwt` to the dev group (mypy overrides for untyped modules), refresh `uv.lock`, and verify by running `import xlrd, charset_normalizer` in the rebuilt backend image
- [ ] 1.2 Create `tests/spreadsheet_samples.py` that builds in memory or in `tmp_path`: a multi-sheet XLSX (one empty sheet, a merged header cell, a title row above the table, dates, a stored 0.1 + 0.2, blank rows and columns), a 250-row XLSX, an all-numbers sheet, a one-sheet XLS, CSVs (comma, `;` + Latin-1 with an accent, quoted comma, UTF-8 with BOM, only blank lines), and truncated XLSX/XLS bytes; verify each one opens (or fails) as intended with a small test

## 2. Reading spreadsheets

- [ ] 2.1 Create `app/pipeline/spreadsheet.py` part 1: `SpreadsheetError` with code, the `Sheet` type, `_read_xlsx` (merged cells filled, cached formula values), `_read_xls` (merged cells, `formatting_info=True`) and `_read_csv` (encoding via `charset-normalizer`, delimiter via `csv.Sniffer` limited to `,;\t|`, BOM dropped), all errors mapped to `spreadsheet_corrupt`; comments for non-obvious choices; unit tests for: XLSX multi-sheet, merged header filled, XLS, CSV `;` + Latin-1, CSV quoted comma, CSV BOM, truncated XLSX and XLS raise `spreadsheet_corrupt`; verify they pass
- [ ] 2.2 Add the cleaning and text rendering to `app/pipeline/spreadsheet.py`: drop empty rows and trailing empty columns, cell-to-text conversion (ISO dates, integers without `.0`, floats rounded and normalised, newlines to spaces), header detection (first row within 20 non-empty rows with at least two filled all-text cells, never a row of identical cells), rows above the header kept as plain lines, page layout with `Sheet: <name>`, header and at most 100 data rows per page with the header repeated on continuation pages; unit tests for: empty rows and columns skipped, dates and numbers (`2026-01-05`, `12`, `120.5`, `0.3`), title above the table, no-header sheet, 250 rows give pages of 100, 100 and 50 with repeated header, merged title is not a header, all-empty workbook and blank-line CSV raise `spreadsheet_empty`; verify they pass
- [ ] 2.3 Add `SpreadsheetReader(path, mime)` with `page_count()` and `pages()` yielding `PageContent` (text, no image), parsing once and caching the page texts, choosing the reader from the detected mime; unit tests for: page count equals pages yielded, numbering runs across sheets in order, an empty sheet is skipped; verify they pass

## 3. Saving pages and wiring the job

- [ ] 3.1 Create `app/services/spreadsheet_ingest.py` (thin wrapper over `ingest_pages`, no FastAPI imports) with DB tests using `FakeStorage` for: multi-sheet workbook saves one `native` row per page with no image and no confidence, `page_count` set, re-run leaves one row per page with the same text, CSV document works end to end; verify they pass
- [ ] 3.2 Wire `workers/tasks.py`: `run_pipeline` gets a `spreadsheet` branch (returns False, no OCR), `SpreadsheetError` joins `PdfError` and `ImageError` in the non-retried branch, the message table gains `spreadsheet_corrupt` and `spreadsheet_empty`; update existing task tests and add tests for: XLSX document ends `COMPLETED` with pages saved and no OCR job queued, damaged XLSX ends `FAILED` `spreadsheet_corrupt` after one attempt, empty workbook ends `FAILED` `spreadsheet_empty` with no pages; verify `make test` passes (the existing tests that used a spreadsheet document as a "does nothing" default must be switched to another type)
- [ ] 3.3 Update `docs/api.md` (error codes `spreadsheet_corrupt` and `spreadsheet_empty`, `page_count` for spreadsheets) and `docs/database-schema.md` (spreadsheet page text layout: sheet label, header, rows per page, `method` native with no image), and verify the documented values match the code

## 4. Integration verification

- [ ] 4.1 Rebuild the stack (`make up`), upload an XLSX with two sheets, an XLS, a `;` Latin-1 CSV and a 250-row CSV, and verify the page rows and text, `COMPLETED` without any `ocr` event, and `page_count` in the document response
- [ ] 4.2 Upload a truncated XLSX and an all-blank CSV and verify `FAILED` with `spreadsheet_corrupt` and `spreadsheet_empty`, each with a single attempt in the history
- [ ] 4.3 Run `make lint`, `make test` (earlier tests included) and `openspec validate add-spreadsheet-parsing --strict`, and verify all pass

## Workflow follow-up

- Update the Phase 1 checkboxes and daily log in `~/Desktop/personal-project/ai-document-intelligence.md`, moving column mapping, LLM header fallback and row-to-invoice records to Phase 2 (`add-invoice-extraction`).
- Archive with `/opsx:archive`, then commit in atomic commits on a `feat/spreadsheet-add-spreadsheet-parsing` branch.
- Push only when asked; open the PR into `main`.
