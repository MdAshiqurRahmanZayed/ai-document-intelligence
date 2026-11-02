"""Builds test spreadsheets in memory so no binary fixtures are committed."""

import io
from datetime import date

import xlwt
from openpyxl import Workbook


def _save(workbook: Workbook) -> bytes:
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def multi_sheet_xlsx() -> bytes:
    """Three sheets: a table under a title, a merged header, and an empty sheet."""
    workbook = Workbook()
    invoices = workbook.active
    assert invoices is not None
    invoices.title = "Invoices"
    invoices["A1"] = "ACME LTD"  # title block above the table
    invoices.append([])
    invoices.append(["Invoice No", "Date", "Amount"])
    invoices.append(["INV-1", date(2026, 1, 5), 120.5])
    invoices.append([])  # blank row between records
    invoices.append(["INV-2", date(2026, 1, 6), 12])
    invoices.append(["INV-3", date(2026, 1, 7), 0.1 + 0.2])  # stored as 0.30000000000000004
    invoices["F6"] = "  "  # whitespace only: counts as an empty trailing column

    merged = workbook.create_sheet("Merged")
    merged["A1"] = "Amounts"
    merged.merge_cells("A1:B1")
    merged["C1"] = "Currency"
    merged.append([10, 20, "EUR"])

    workbook.create_sheet("Empty")
    return _save(workbook)


def empty_xlsx() -> bytes:
    return _save(Workbook())  # one sheet with nothing in it


def big_xlsx(rows: int = 250) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.title = "Big"
    sheet.append(["Line", "Description"])
    for n in range(1, rows + 1):
        sheet.append([f"L{n}", f"item {n}"])
    return _save(workbook)


def numbers_xlsx() -> bytes:
    """No text anywhere, so no row can be a header."""
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.append([1, 2, 3])
    sheet.append([4, 5, 6])
    return _save(workbook)


def title_only_xlsx() -> bytes:
    """A merged title across three columns: identical cells must not be taken as a header."""
    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet["A1"] = "QUARTERLY REPORT"
    sheet.merge_cells("A1:C1")
    sheet.append(["Item", "Qty", "Price"])
    sheet.append(["Pen", 3, 1.5])
    return _save(workbook)


def xls() -> bytes:
    """One-sheet legacy workbook (xlwt is the only library that can write this format)."""
    workbook = xlwt.Workbook()
    sheet = workbook.add_sheet("Legacy")
    for col, value in enumerate(["Item", "Qty"]):
        sheet.write(0, col, value)
    sheet.write(1, 0, "Pen")
    sheet.write(1, 1, 3)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def csv_semicolon_latin1() -> bytes:
    return "Lieferant;Betrag\nMüller GmbH;120,50\n".encode("latin-1")


def csv_quoted_comma() -> bytes:
    return b'Name,Amount\n"Acme, Inc.",100\n'


def csv_utf8_bom() -> bytes:
    return "﻿Name,Amount\nAcme,1\n".encode()


def csv_blank() -> bytes:
    return b"\n\n  \n"


def truncated(data: bytes) -> bytes:
    return data[: len(data) // 2]
