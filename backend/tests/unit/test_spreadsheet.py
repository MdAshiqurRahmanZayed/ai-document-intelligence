from pathlib import Path

import pytest

from app.pipeline.spreadsheet import SpreadsheetError, SpreadsheetReader
from tests import spreadsheet_samples as samples

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
XLS = "application/vnd.ms-excel"
CSV = "text/csv"


def read(tmp_path: Path, data: bytes, mime: str, name: str = "Sheet1") -> list[str]:
    path = tmp_path / "document"
    path.write_bytes(data)
    return [page.text or "" for page in SpreadsheetReader(path, mime, name).pages()]


def test_multi_sheet_workbook_gives_a_page_per_sheet_and_skips_the_empty_one(
    tmp_path: Path,
) -> None:
    pages = read(tmp_path, samples.multi_sheet_xlsx(), XLSX)

    # Title kept above the header, blank row and column dropped, dates in ISO 8601, whole
    # numbers without ".0" and 0.1 + 0.2 without float noise.
    assert pages[0] == (
        "Sheet: Invoices\n"
        "ACME LTD\n"
        "Invoice No | Date | Amount\n"
        "INV-1 | 2026-01-05 | 120.5\n"
        "INV-2 | 2026-01-06 | 12\n"
        "INV-3 | 2026-01-07 | 0.3"
    )
    # The merged header cell shows its value in both columns it covers.
    assert pages[1] == "Sheet: Merged\nAmounts | Amounts | Currency\n10 | 20 | EUR"
    assert len(pages) == 2


def test_legacy_xls(tmp_path: Path) -> None:
    assert read(tmp_path, samples.xls(), XLS) == ["Sheet: Legacy\nItem | Qty\nPen | 3"]


def test_csv_semicolon_latin1_keeps_the_accent_and_splits_cells(tmp_path: Path) -> None:
    pages = read(tmp_path, samples.csv_semicolon_latin1(), CSV, "invoice")
    assert pages == ["Sheet: invoice\nLieferant | Betrag\nMüller GmbH | 120,50"]


def test_csv_quoted_delimiter_stays_one_cell(tmp_path: Path) -> None:
    pages = read(tmp_path, samples.csv_quoted_comma(), CSV)
    assert pages == ["Sheet: Sheet1\nName | Amount\nAcme, Inc. | 100"]


def test_csv_byte_order_mark_is_dropped(tmp_path: Path) -> None:
    pages = read(tmp_path, samples.csv_utf8_bom(), CSV)
    assert pages == ["Sheet: Sheet1\nName | Amount\nAcme | 1"]


def test_sheet_without_a_text_row_has_no_header(tmp_path: Path) -> None:
    pages = read(tmp_path, samples.numbers_xlsx(), XLSX)
    assert pages == ["Sheet: Sheet\n1 | 2 | 3\n4 | 5 | 6"]


def test_merged_title_is_not_taken_for_the_header(tmp_path: Path) -> None:
    pages = read(tmp_path, samples.title_only_xlsx(), XLSX)
    assert pages == ["Sheet: Sheet\nQUARTERLY REPORT\nItem | Qty | Price\nPen | 3 | 1.5"]


def test_long_sheet_is_split_with_the_header_repeated(tmp_path: Path) -> None:
    pages = read(tmp_path, samples.big_xlsx(250), XLSX)

    assert [len(p.splitlines()) - 2 for p in pages] == [100, 100, 50]  # data rows per page
    assert pages[0].startswith("Sheet: Big\nLine | Description\nL1 | item 1")
    assert pages[1].startswith("Sheet: Big (continued)\nLine | Description\nL101 | item 101")
    assert pages[2].endswith("L250 | item 250")


@pytest.mark.parametrize("data", [samples.truncated(samples.multi_sheet_xlsx())])
def test_truncated_xlsx_is_corrupt(tmp_path: Path, data: bytes) -> None:
    with pytest.raises(SpreadsheetError) as error:
        read(tmp_path, data, XLSX)
    assert error.value.code == "spreadsheet_corrupt"


def test_truncated_xls_is_corrupt(tmp_path: Path) -> None:
    with pytest.raises(SpreadsheetError) as error:
        read(tmp_path, samples.truncated(samples.xls()), XLS)
    assert error.value.code == "spreadsheet_corrupt"


def test_unknown_type_is_corrupt(tmp_path: Path) -> None:
    with pytest.raises(SpreadsheetError) as error:
        read(tmp_path, b"x", "application/pdf")
    assert error.value.code == "spreadsheet_corrupt"


def test_workbook_and_csv_without_data_are_empty(tmp_path: Path) -> None:
    for data, mime in [(samples.empty_xlsx(), XLSX), (samples.csv_blank(), CSV)]:
        with pytest.raises(SpreadsheetError) as error:
            read(tmp_path, data, mime)
        assert error.value.code == "spreadsheet_empty"


def test_page_count_matches_the_pages_and_numbering_runs_across_sheets(tmp_path: Path) -> None:
    path = tmp_path / "document"
    path.write_bytes(samples.multi_sheet_xlsx())
    reader = SpreadsheetReader(path, XLSX)

    pages = list(reader.pages())

    assert reader.page_count() == len(pages) == 2
    assert [p.page_no for p in pages] == [1, 2]
    assert all(p.image is None for p in pages)
