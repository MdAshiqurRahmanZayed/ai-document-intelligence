# Design

## Context

The ingest task (`workers/tasks.py`) dispatches on `documents.source_type`; `spreadsheet` currently falls into the `else` branch of `run_pipeline` and does nothing. Upload already detects the three formats from their bytes (`services/filetypes.py`: XLSX by `xl/workbook.xml` in the zip, XLS by the OLE signature plus extension, CSV by extension and no NUL bytes). `services/pages.py` (`ingest_pages`) already downloads the stored file, sets `page_count`, and saves page rows in batches from any reader that offers `page_count()` and `pages()` yielding `PageContent`; rows without an image are saved as `native`. `openpyxl` is already a dependency. See `proposal.md` for motivation and `specs/` for requirements.

## Goals / Non-Goals

**Goals:**
- Reuse the shared page-saving path so spreadsheets get idempotent upserts for free.
- A pure, testable parser: file path in, page texts out, no database or storage imports.
- Text that keeps the table structure (header, one row per line) so the Phase 2 LLM step and full-text search can use it.

**Non-Goals:**
- Column mapping, row-to-invoice conversion, LLM fallback (moved to `add-invoice-extraction`, see proposal).
- Streaming parse of very large workbooks; a size or row cap (accepted risk below).

## Decisions

**D1. Direct readers, no pandas.** `openpyxl` for XLSX, `xlrd` for XLS, the standard `csv` module for CSV, `charset-normalizer` for encoding. pandas would add a heavy dependency and hides what this change needs: merged cells, a header that is not on row 1, and the original cell types. Alternative: pandas `read_excel`/`read_csv` with `header=None`; rejected for those reasons.

**D2. One module with one class per format behind one function.** `pipeline/spreadsheet.py` has `SpreadsheetError` (carries a code), small readers `_read_xlsx`, `_read_xls`, `_read_csv` that each return `list[Sheet]` (`Sheet` = name plus rows of plain Python values), and `SpreadsheetReader(path, filename)` with the `page_count()` / `pages()` shape that `ingest_pages` expects. The format is chosen from the stored file's extension (`.xlsx`, `.xls`, `.csv`); upload already guaranteed the bytes match it. The pure module imports nothing from FastAPI, the database or storage.

**D3. The workbook is read fully into memory, once.** Merged-cell filling needs openpyxl's normal (not read-only) mode, and XLS is always loaded whole by `xlrd`. `SpreadsheetReader` reads and renders the sheets on first use and caches the page texts, so `page_count()` (needed before pages are saved) and `pages()` share one parse. Memory is bounded by the upload limit (100 MB) only; see risks. `data_only=True` makes openpyxl return the value Excel cached for a formula instead of the formula text.

**D4. Cleaning rules, in order.** For each sheet: (1) fill merged ranges (openpyxl `merged_cells.ranges`; `xlrd` `merged_cells` needs `formatting_info=True`) so every covered cell holds the top-left value; (2) drop rows whose cells are all empty or whitespace; (3) trim trailing empty columns across the whole sheet (to the right-most non-empty column); (4) a sheet with no rows left is skipped. Cell values become text with one function: `None` becomes empty, `datetime` becomes ISO 8601 (date only when the time is midnight), `bool` becomes `true`/`false`, `int` or an integral `float` becomes an integer string, other floats are rounded to 10 decimal places, converted to `Decimal` and written without exponent or trailing zeros (so a stored `0.30000000000000004` reads `0.3`), strings are stripped and internal newlines become spaces, and ` | ` inside a value stays as is (a cell is never quoted, because the text is for reading and for the LLM, not for round-tripping). Money is therefore never routed through binary float formatting for display. Alternative: write raw `str(value)`; rejected, it prints `120.0` and float noise.

**D5. Header detection is a small heuristic.** Among the first 20 non-empty rows, the header is the first row that has at least two filled cells and where every filled cell is text (not a number, date or bool). Rows above it (a company name, an address) are kept as plain lines above the header on the first page only; they are not repeated. No qualifying row means no header: every row is data and no header line is written. Merged title cells are already filled by D4, so a title merged across several columns would look like several equal text cells; to avoid mistaking it for a header, a row whose filled cells are all identical is never a header. Alternative: always use row 1; rejected, real exports often start with a title block.

**D6. Page layout.** A page's text is `Sheet: <name>`, then (first page only) the rows above the header, then the header line, then up to 100 data rows. Continuation pages of a sheet repeat `Sheet: <name> (continued)` and the header, so every page stands alone for the LLM and for search. A single constant `ROWS_PER_PAGE = 100` sets the split; pages of that size stay far below LLM context limits while keeping page numbers meaningful. Page numbers run across all sheets in order. Cells are joined with ` | `. Alternatives: one page per sheet (a 50 000-row sheet becomes one unusable page), markdown tables (padding noise, no gain).

**D7. CSV.** Bytes are decoded with `charset-normalizer`'s best match, falling back to UTF-8 with replacement if it finds none; a UTF-8 BOM is dropped. The delimiter comes from `csv.Sniffer` on the first 8 KiB restricted to `,;\t|`, falling back to `,`. The sheet is named after the document's stored filename stem. Quoted fields and embedded newlines are handled by the `csv` module. Alternative: assume UTF-8 and comma; rejected, European invoice exports are commonly Latin-1 with `;`.

**D8. Errors.** `SpreadsheetError("spreadsheet_corrupt")` wraps everything the readers raise on a bad file (`zipfile.BadZipFile`, `KeyError`, `xlrd.XLRDError`, `openpyxl` exceptions, `csv.Error`, decode failures); `SpreadsheetError("spreadsheet_empty")` is raised when no sheet has data left after D4. `run_pipeline` gains a `spreadsheet` branch; `_run` adds `SpreadsheetError` to the `PdfError`/`ImageError` branch (no retry) and the message table gains both codes. A spreadsheet never has scanned pages, so `run_pipeline` returns False and the document becomes `COMPLETED` in the ingest job.

**D9. Service.** `services/spreadsheet_ingest.py` is a thin wrapper like `image_ingest.py`: `ingest_pages(session, storage, document, open_reader)` with an `open_reader` that builds `SpreadsheetReader(path, document.filename)`. Because the temp file downloaded by `ingest_pages` is named `document`, the reader gets the extension from the document's detected `mime` instead of the path (mapping mime to reader), so it never trusts the client filename for the format.

**D10. Test files are generated.** Fixtures are built in `tests/spreadsheet_samples.py`: XLSX with `openpyxl` (multi-sheet, merged header, title block, empty sheet, dates and floats), XLS with `xlwt` (no library can write XLS otherwise; dev dependency only) and CSVs by encoding strings (`;` + Latin-1, quoted comma, BOM, blank lines). Damaged files are the valid bytes cut in half.

## Risks / Trade-offs

- [A huge workbook (100 MB of XLSX can expand to gigabytes, or a zip bomb) exhausts worker memory] -> Accepted for now, bounded by the upload limit. Row and cell caps are an obvious follow-up for the hardening phase; the reader's single load point (D3) is where a cap would go.
- [Header heuristic misreads an odd sheet (all-text data table, header on row 25)] -> The text still holds every row; a wrong header only changes labelling, and Phase 2 extraction reads the whole page. Constants (`HEADER_SEARCH_ROWS = 20`) are named and tested with positive and negative samples.
- [`xlrd` 2.x reads only `.xls`, and merged cells in XLS need `formatting_info=True`, which is slower] -> XLS is a legacy format with small files in practice; the flag is only used for XLS.
- [Cached formula values are missing when a file was written by a library that never calculated them] -> Those cells read as empty; stated as out of scope. A re-save in Excel fixes the file.
- [Charset detection guesses wrong on short files] -> Latin-1 and UTF-8 are covered by tests; a wrong guess changes accents, never the table structure.
- [`xlwt` is only a test-time dependency for building an XLS fixture] -> Dev group only; if it proves unmaintained, the XLS fixture can be a small committed binary file instead.

## Migration Plan

No schema change and no new service. Add the two runtime dependencies and one dev dependency, rebuild the backend images (`make up`). Spreadsheet documents uploaded before this change are `COMPLETED` with no pages; re-upload them (a failed or incomplete document is retried by re-uploading the same file) or run `ingest_document.delay(<id>)` from a shell. Rollback: revert the code; the extra page rows are harmless.
