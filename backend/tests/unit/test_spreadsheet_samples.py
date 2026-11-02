import io
import zipfile

import pytest
import xlrd
from openpyxl import load_workbook

from tests import spreadsheet_samples as samples


def test_xlsx_samples_open_as_intended() -> None:
    workbook = load_workbook(io.BytesIO(samples.multi_sheet_xlsx()))
    assert workbook.sheetnames == ["Invoices", "Merged", "Empty"]
    assert load_workbook(io.BytesIO(samples.big_xlsx())).active.max_row == 251
    assert load_workbook(io.BytesIO(samples.numbers_xlsx())).active.max_row == 2


def test_xls_sample_opens() -> None:
    book = xlrd.open_workbook(file_contents=samples.xls())
    assert book.sheet_names() == ["Legacy"]


def test_text_samples_decode_as_intended() -> None:
    assert "Müller" in samples.csv_semicolon_latin1().decode("latin-1")
    assert samples.csv_utf8_bom().startswith(b"\xef\xbb\xbf")


def test_truncated_workbooks_fail_to_open() -> None:
    with pytest.raises(zipfile.BadZipFile):
        load_workbook(io.BytesIO(samples.truncated(samples.multi_sheet_xlsx())))
    with pytest.raises(Exception):  # noqa: B017  (which error xlrd raises is for the reader to map)
        xlrd.open_workbook(file_contents=samples.truncated(samples.xls()))
