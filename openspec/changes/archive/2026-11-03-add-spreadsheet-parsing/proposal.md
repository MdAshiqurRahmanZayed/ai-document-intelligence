# Proposal

## Why

Spreadsheets (XLSX, XLS, CSV) are accepted at upload but the ingest job does nothing for them: the document ends `COMPLETED` with no pages. PDFs and images now produce page text; spreadsheets are the last Phase 1 input type, and without them a whole class of invoice exports cannot reach the extraction phase.

## What Changes

- Parse spreadsheet documents: every sheet of an XLSX or XLS, and CSV files of any common encoding and delimiter (`;`, `,`, tab, `|`).
- Turn each sheet into one or more page records with method `native` and readable text: a sheet label, the detected header row, then one line per data row. Long sheets are split into pages of 100 data rows with the header repeated, so later stages never see one giant page.
- Detect the header row (it need not be the first row), skip empty rows and columns, fill merged cells, and show dates as ISO 8601 and numbers without float artefacts.
- Fail unreadable files with clear codes: `spreadsheet_corrupt` (cannot be opened) and `spreadsheet_empty` (opens but holds no data). Not retried.
- Document the new error codes and the spreadsheet page layout in the API and schema docs.

Out of scope:
- Deterministic column mapping (synonym dictionary), LLM mapping for unknown headers, and turning rows or row groups into invoice records. They need the `extractions` table and the LLM client from Phase 2 and move to `add-invoice-extraction`.
- Formula evaluation (cached cell values are read as saved), charts, images, comments, macros, and password-protected workbooks.
- A row or cell limit for huge workbooks (the upload size limit is the only guard for now).
- OCR, LLM extraction, validation, search and the review UI.

## Capabilities

### New Capabilities
- `spreadsheet-ingestion`: spreadsheet documents become page records with readable table text; unreadable or empty spreadsheets fail with a clear code.

### Modified Capabilities

None. Document status behaviour is unchanged: a spreadsheet document ends `COMPLETED` as soon as its pages are saved, because it never needs OCR.

## Impact

- Code: new `pipeline/spreadsheet.py` and `services/spreadsheet_ingest.py`; `workers/tasks.py` (dispatch branch, `SpreadsheetError` in the non-retried branch, message table).
- Dependencies: `xlrd` (legacy XLS) and `charset-normalizer` (CSV encoding); `openpyxl` is already a dependency. pandas is not added: the parser needs raw cell control (merged cells, header row search), which pandas hides.
- Data: no schema change; spreadsheet pages use `method = native` with `image_key` and `ocr_confidence` empty.
- Docs: `docs/api.md` (error codes, `page_count` for spreadsheets), `docs/database-schema.md` (spreadsheet page text layout).
