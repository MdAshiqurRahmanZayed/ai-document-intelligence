"""Smallest byte strings that carry each supported format's signature."""

import io
import zipfile

from openpyxl import Workbook

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32
TIFF = b"II*\x00" + b"\x00" * 32
OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 32
CSV = b"invoice_no,total\nINV-1,10.00\n"


def pdf(tag: str = "") -> bytes:
    # The tag makes otherwise identical PDFs differ, so they get different hashes.
    return b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF\n" + tag.encode()


def xlsx() -> bytes:
    workbook = Workbook()
    workbook.active.append(["invoice_no", "total"])
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def zip_without_workbook() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("note.txt", "not a spreadsheet")
    return buffer.getvalue()
