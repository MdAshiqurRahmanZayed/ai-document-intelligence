from pathlib import Path

from app.pipeline.ocr import OcrEngine
from app.pipeline.pdf import PdfReader
from app.pipeline.spreadsheet import SpreadsheetReader
from tests import invoice_samples as samples

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def pdf_text(tmp_path: Path, data: bytes) -> str:
    path = tmp_path / "invoice.pdf"
    path.write_bytes(data)
    return "\n".join(page.text or "" for page in PdfReader(path).pages())


def test_the_digital_pdf_text_contains_its_own_values(tmp_path: Path) -> None:
    text = pdf_text(tmp_path, samples.invoice_pdf())

    for value in ("INV-1042", samples.SUPPLIER, samples.CUSTOMER, "120.00", "Widget", "EUR"):
        assert value in text


def test_the_scanned_image_is_readable_by_ocr() -> None:
    result = OcrEngine().read(samples.invoice_png())

    assert "INV-1042" in result.text and "120.00" in result.text


def test_the_spreadsheet_states_the_same_invoice(tmp_path: Path) -> None:
    path = tmp_path / "invoice.xlsx"
    path.write_bytes(samples.invoice_xlsx())

    text = "\n".join(page.text or "" for page in SpreadsheetReader(path, XLSX).pages())

    for value in ("INV-1042", samples.SUPPLIER, "120.00", "Widget"):
        assert value in text


def test_the_problem_invoices_differ_where_they_should(tmp_path: Path) -> None:
    assert "130.00" in pdf_text(tmp_path, samples.wrong_total_pdf())  # 100 + 20 is not 130
    duplicate = pdf_text(tmp_path, samples.duplicate_pdf())
    assert "INV-1042" in duplicate and samples.SUPPLIER in duplicate and "60.00" in duplicate
    assert "INV-1042" not in pdf_text(tmp_path, samples.letter_pdf())
