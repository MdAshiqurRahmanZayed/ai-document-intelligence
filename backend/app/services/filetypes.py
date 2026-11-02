import zipfile
from dataclasses import dataclass
from typing import BinaryIO


@dataclass(frozen=True)
class DetectedType:
    mime: str
    extension: str
    source_type: str  # pdf | image | spreadsheet


_PDF = DetectedType("application/pdf", ".pdf", "pdf")
_JPEG = DetectedType("image/jpeg", ".jpg", "image")
_PNG = DetectedType("image/png", ".png", "image")
_TIFF = DetectedType("image/tiff", ".tiff", "image")
_XLSX = DetectedType(
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".xlsx", "spreadsheet"
)
_XLS = DetectedType("application/vnd.ms-excel", ".xls", "spreadsheet")
_CSV = DetectedType("text/csv", ".csv", "spreadsheet")

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_OLE_SIGNATURE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


def detect_type(head: bytes, filename: str, fileobj: BinaryIO) -> DetectedType | None:
    """Decide the file type from its bytes. The filename is only a tiebreaker for the two
    formats that cannot be recognised by content alone (legacy XLS and CSV).

    `fileobj` must be seekable; it is rewound before returning.
    """
    name = filename.lower()

    if head.startswith(b"%PDF-"):
        return _PDF
    if head.startswith(b"\xff\xd8\xff"):
        return _JPEG
    if head.startswith(_PNG_SIGNATURE):
        return _PNG
    if head.startswith((b"II*\x00", b"MM\x00*")):
        return _TIFF
    if head.startswith(b"PK\x03\x04"):
        return _XLSX if _is_xlsx(fileobj) else None
    # OLE2 also wraps Word, PowerPoint and others, so the extension must agree.
    if head.startswith(_OLE_SIGNATURE):
        return _XLS if name.endswith(".xls") else None
    # CSV has no signature. Accept text-like content (no NUL bytes) named .csv.
    if name.endswith(".csv") and b"\x00" not in head:
        return _CSV
    return None


def _is_xlsx(fileobj: BinaryIO) -> bool:
    # An xlsx is a zip with xl/workbook.xml. Reading the entry list only touches the zip's
    # central directory; nothing is decompressed.
    try:
        with zipfile.ZipFile(fileobj) as archive:
            return "xl/workbook.xml" in archive.namelist()
    except zipfile.BadZipFile:
        return False
    finally:
        fileobj.seek(0)
