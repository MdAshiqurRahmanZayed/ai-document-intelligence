"""Reads a PDF file page by page. Pure: no database, storage or web imports."""

import io
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import pypdfium2 as pdfium
import pypdfium2.raw as pdfium_c

# A page with fewer non-whitespace characters than this is treated as a scan. Stray page
# numbers or stamps on an otherwise image-only page stay below it; real invoice text does not.
SCANNED_MAX_CHARS = 20

RENDER_DPI = 300
PDF_POINTS_PER_INCH = 72  # PDF page sizes are in points

# Longest allowed image side. An A4 page at 300 DPI is about 3500px; the cap only bites on
# poster-sized pages, which would otherwise need hundreds of MB for one bitmap.
MAX_IMAGE_SIDE = 5000


class PdfError(Exception):
    """The PDF cannot be used. `code` is stored on the document and shown to the user."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass
class PageContent:
    page_no: int  # 1-based
    text: str | None  # None for scanned pages
    image: bytes | None  # PNG, only for scanned pages


def page_count(path: Path) -> int:
    with _open(path) as pdf:
        return len(pdf)


def extract_pages(path: Path) -> Generator[PageContent]:
    """Yield pages lazily so only one page (and its bitmap) is in memory at a time."""
    with _open(path) as pdf:
        for index in range(len(pdf)):
            page = pdf[index]
            try:
                yield _read_page(page, index + 1)
            finally:
                page.close()


@contextmanager
def _open(path: Path) -> Generator[pdfium.PdfDocument]:
    try:
        pdf = pdfium.PdfDocument(path)
    except pdfium.PdfiumError as exc:
        # PDFium reports a missing password with its own code; anything else that stops the
        # file from opening (truncated, garbled, empty page tree) is damage.
        if exc.err_code == pdfium_c.FPDF_ERR_PASSWORD:
            raise PdfError("pdf_encrypted") from exc
        raise PdfError("pdf_corrupt") from exc
    try:
        if len(pdf) == 0:
            raise PdfError("pdf_empty")
        yield pdf
    finally:
        pdf.close()


def _read_page(page: pdfium.PdfPage, page_no: int) -> PageContent:
    textpage = page.get_textpage()
    try:
        # PostgreSQL text cannot store NUL, and some PDFs emit it.
        text = textpage.get_text_range().replace("\x00", "")
    finally:
        textpage.close()

    if len("".join(text.split())) >= SCANNED_MAX_CHARS:
        return PageContent(page_no, text, None)
    return PageContent(page_no, None, _render_png(page))


def _render_png(page: pdfium.PdfPage) -> bytes:
    width, height = page.get_size()
    scale = min(RENDER_DPI / PDF_POINTS_PER_INCH, MAX_IMAGE_SIDE / max(width, height))
    bitmap = page.render(scale=scale)
    buffer = io.BytesIO()
    bitmap.to_pil().save(buffer, format="PNG")
    return buffer.getvalue()
