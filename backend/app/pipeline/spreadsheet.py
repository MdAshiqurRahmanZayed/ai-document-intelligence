"""Reads spreadsheets (XLSX, XLS, CSV) into page texts. Pure: no database, storage or web."""

import csv
import io
import math
import re
from collections.abc import Callable, Generator
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from pathlib import Path
from typing import Any

import xlrd
from charset_normalizer import from_bytes
from openpyxl import load_workbook

from app.pipeline.pdf import PageContent

# Data rows per page: small enough for later stages to take a page whole, large enough that
# page numbers stay meaningful.
ROWS_PER_PAGE = 100
# Title and address blocks above a table are short; looking further risks picking a data row.
HEADER_SEARCH_ROWS = 20
CSV_DELIMITERS = ",;\t|"


class SpreadsheetError(Exception):
    """The spreadsheet cannot be used. `code` is stored on the document and shown to the user."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass
class Sheet:
    name: str
    rows: list[list[Any]]  # raw cell values: str, int, float, bool, datetime or None


def _read_xlsx(path: Path, name: str) -> list[Sheet]:
    # Not read-only mode: merged ranges are only available in the normal mode.
    # data_only returns the value Excel saved for a formula, not the formula text.
    # Opened as a file object because openpyxl refuses a path without an .xlsx extension, and
    # the stored file is a temp file with no extension.
    with path.open("rb") as file:
        workbook = load_workbook(file, data_only=True)
    sheets = []
    for sheet in workbook.worksheets:
        rows = [
            list(row)
            for row in sheet.iter_rows(
                min_row=1,
                max_row=sheet.max_row,
                min_col=1,
                max_col=sheet.max_column,
                values_only=True,
            )
        ]
        for merged in sheet.merged_cells.ranges:
            value = sheet.cell(merged.min_row, merged.min_col).value
            for r in range(merged.min_row, merged.max_row + 1):
                for c in range(merged.min_col, merged.max_col + 1):
                    rows[r - 1][c - 1] = value
        sheets.append(Sheet(sheet.title, rows))
    return sheets


def _read_xls(path: Path, name: str) -> list[Sheet]:
    # formatting_info is what exposes merged cells in the legacy format (slower, but XLS files
    # are small in practice).
    book = xlrd.open_workbook(str(path), formatting_info=True)
    sheets = []
    for sheet in book.sheets():
        rows: list[list[Any]] = [
            [_xls_value(book, sheet.cell(r, c)) for c in range(sheet.ncols)]
            for r in range(sheet.nrows)
        ]
        for row_lo, row_hi, col_lo, col_hi in sheet.merged_cells:  # upper bounds are exclusive
            value = rows[row_lo][col_lo]
            for r in range(row_lo, row_hi):
                for c in range(col_lo, col_hi):
                    rows[r][c] = value
        sheets.append(Sheet(sheet.name, rows))
    return sheets


def _xls_value(book: Any, cell: Any) -> Any:
    if cell.ctype == xlrd.XL_CELL_DATE:
        return xlrd.xldate_as_datetime(cell.value, book.datemode)
    if cell.ctype == xlrd.XL_CELL_BOOLEAN:
        return bool(cell.value)
    if cell.ctype in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK, xlrd.XL_CELL_ERROR):
        return None
    return cell.value


def _read_csv(path: Path, name: str) -> list[Sheet]:
    raw = path.read_bytes()
    best = from_bytes(raw).best()
    # No confident guess (very short or odd file): UTF-8 with replacement keeps the structure.
    text = str(best) if best else raw.decode("utf-8", errors="replace")
    text = text.lstrip("﻿")  # byte-order mark
    try:
        delimiter = csv.Sniffer().sniff(text[:8192], delimiters=CSV_DELIMITERS).delimiter
    except csv.Error:
        delimiter = ","
    rows = list(csv.reader(io.StringIO(text, newline=""), delimiter=delimiter))
    return [Sheet(name, rows)]


_READERS: dict[str, Callable[[Path, str], list[Sheet]]] = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": _read_xlsx,
    "application/vnd.ms-excel": _read_xls,
    "text/csv": _read_csv,
}


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _is_text(value: Any) -> bool:
    # CSV cells are all strings, so numbers written as text ("120,50", "1 000.00") must not
    # count as text or a data row would be taken for a header.
    return isinstance(value, str) and not re.fullmatch(r"[-+]?[\d\s.,]+", value.strip())


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):  # before int: bool is an int subclass
        return "true" if value else "false"
    if isinstance(value, datetime):
        # Date only when the time is midnight: most invoice dates carry no time.
        return value.date().isoformat() if value.time() == time(0) else value.isoformat()
    if isinstance(value, date | time):
        return value.isoformat()
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            return ""
        if value.is_integer():
            return str(int(value))
        # Rounding drops binary noise (0.1 + 0.2), then Decimal writes it without an exponent.
        return format(Decimal(repr(round(value, 10))).normalize(), "f")
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    return " ".join(str(value).split())  # one line: newlines and runs of spaces become one space


def _clean(rows: list[list[Any]]) -> list[list[Any]]:
    kept = [row for row in rows if not all(_is_blank(v) for v in row)]
    width = max(
        (i + 1 for row in kept for i, v in enumerate(row) if not _is_blank(v)),
        default=0,
    )
    return [row[:width] + [None] * (width - len(row)) for row in kept]


def _header_index(rows: list[list[Any]]) -> int | None:
    for index, row in enumerate(rows[:HEADER_SEARCH_ROWS]):
        filled = [v for v in row if not _is_blank(v)]
        # Identical cells are a merged title, not column names.
        if len(filled) >= 2 and all(_is_text(v) for v in filled) and len(set(filled)) > 1:
            return index
    return None


def _line(row: list[Any], *, skip_blank: bool = False) -> str:
    cells = [_text(v) for v in row]
    if not skip_blank:
        return " | ".join(cells)
    # A merged title fills several cells with one value: show it once.
    shown = [c for c in cells if c]
    return " | ".join(c for i, c in enumerate(shown) if i == 0 or c != shown[i - 1])


def _render(sheet: Sheet) -> list[str]:
    rows = _clean(sheet.rows)
    if not rows:
        return []
    header = _header_index(rows)
    above = [_line(r, skip_blank=True) for r in rows[: header or 0]]
    header_line = None if header is None else _line(rows[header])
    data = rows if header is None else rows[header + 1 :]

    pages = []
    for number, start in enumerate(range(0, max(len(data), 1), ROWS_PER_PAGE)):
        lines = [f"Sheet: {sheet.name}" + (" (continued)" if number else "")]
        if number == 0:
            lines += above
        if header_line is not None:
            lines.append(header_line)
        lines += [_line(r) for r in data[start : start + ROWS_PER_PAGE]]
        pages.append("\n".join(lines))
    return pages


class SpreadsheetReader:
    """Turns one spreadsheet file into page texts. The file is parsed once, on first use."""

    def __init__(self, path: Path, mime: str, name: str = "Sheet1") -> None:
        self.path, self.mime, self.name = path, mime, name
        self._pages: list[str] | None = None

    def _load(self) -> list[str]:
        if self._pages is None:
            reader = _READERS.get(self.mime)
            try:
                if reader is None:
                    raise ValueError(f"not a spreadsheet type: {self.mime}")
                sheets = reader(self.path, self.name)
            except Exception as exc:
                # The parsers raise many unrelated types on damaged input (zip, xml, OLE, csv,
                # decoding); every one of them means the file cannot be used.
                raise SpreadsheetError("spreadsheet_corrupt") from exc
            pages = [page for sheet in sheets for page in _render(sheet)]
            if not pages:
                raise SpreadsheetError("spreadsheet_empty")
            self._pages = pages
        return self._pages

    def page_count(self) -> int:
        return len(self._load())

    def pages(self) -> Generator[PageContent]:
        for number, text in enumerate(self._load(), start=1):
            yield PageContent(number, text, None)
