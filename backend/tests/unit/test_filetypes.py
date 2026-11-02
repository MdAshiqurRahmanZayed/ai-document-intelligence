import io

import pytest

from app.services.filetypes import DetectedType, detect_type
from tests import samples


def detect(data: bytes, filename: str) -> DetectedType | None:
    return detect_type(data, filename, io.BytesIO(data))


@pytest.mark.parametrize(
    ("data", "filename", "mime"),
    [
        (samples.pdf(), "a.pdf", "application/pdf"),
        (samples.JPEG, "a.jpg", "image/jpeg"),
        (samples.PNG, "a.png", "image/png"),
        (samples.TIFF, "a.tiff", "image/tiff"),
        (b"MM\x00*" + b"\x00" * 8, "a.tif", "image/tiff"),
        (
            samples.xlsx(),
            "a.xlsx",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ),
        (samples.OLE, "a.xls", "application/vnd.ms-excel"),
        (samples.CSV, "a.csv", "text/csv"),
    ],
)
def test_detects_each_supported_type(data: bytes, filename: str, mime: str) -> None:
    detected = detect(data, filename)
    assert detected is not None
    assert detected.mime == mime


def test_binary_signature_wins_over_filename() -> None:
    detected = detect(samples.PNG, "scan.pdf")
    assert detected is not None
    assert detected.mime == "image/png"
    assert detected.extension == ".png"


def test_pdf_named_jpg_is_still_a_pdf() -> None:
    detected = detect(samples.pdf(), "scan.jpg")
    assert detected is not None
    assert (detected.mime, detected.extension) == ("application/pdf", ".pdf")


@pytest.mark.parametrize(
    ("data", "filename"),
    [
        (samples.zip_without_workbook(), "invoice.pdf"),  # renamed zip
        (samples.zip_without_workbook(), "book.xlsx"),  # zip that is not a spreadsheet
        (b"\x13\x07random bytes, not a pdf", "scan.pdf"),
        (samples.OLE, "report.doc"),  # OLE container without the .xls name
        (b"a,b\x00c\n", "data.csv"),  # NUL byte: binary, not text
        (samples.CSV, "data.txt"),  # text, but not a type we accept
        (b"", "empty.pdf"),
    ],
)
def test_rejects_everything_else(data: bytes, filename: str) -> None:
    assert detect(data, filename) is None


def test_rewinds_the_file_after_inspecting_a_zip() -> None:
    data = samples.xlsx()
    fileobj = io.BytesIO(data)
    assert detect_type(data, "a.xlsx", fileobj) is not None
    assert fileobj.tell() == 0
