import io
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

from app.pipeline.pdf import PdfError, PdfReader
from tests import pdf_samples as samples


def write(tmp_path: Path, content: bytes) -> Path:
    path = tmp_path / "doc.pdf"
    path.write_bytes(content)
    return path


def png_size(data: bytes) -> tuple[int, int]:
    return Image.open(io.BytesIO(data)).size


def test_text_pages_are_extracted_without_images(tmp_path: Path) -> None:
    path = write(tmp_path, samples.text_pdf(3))

    pages = list(PdfReader(path).pages())

    assert PdfReader(path).page_count() == 3
    assert [p.page_no for p in pages] == [1, 2, 3]
    assert all(p.text and p.image is None for p in pages)
    assert "page 2" in (pages[1].text or "")


def test_image_only_page_is_scanned_and_rendered(tmp_path: Path) -> None:
    (page,) = PdfReader(write(tmp_path, samples.scanned_pdf())).pages()

    assert page.text is None
    assert page.image is not None and page.image.startswith(b"\x89PNG")


def test_mixed_pdf_renders_only_the_scanned_page(tmp_path: Path) -> None:
    pages = list(PdfReader(write(tmp_path, samples.mixed_pdf())).pages())

    assert [p.image is not None for p in pages] == [False, True, False]


def test_render_is_300_dpi(tmp_path: Path) -> None:
    (page,) = PdfReader(write(tmp_path, samples.scanned_pdf())).pages()

    assert page.image is not None
    width, height = png_size(page.image)
    assert (width, height) == pytest.approx((595 * 300 / 72, 842 * 300 / 72), abs=2)  # A4


def test_oversized_page_is_scaled_down_to_the_cap(tmp_path: Path) -> None:
    poster = samples.build_pdf([None], size=(2000, 3000))  # would be 12500px at 300 DPI
    (page,) = PdfReader(write(tmp_path, poster)).pages()

    assert page.image is not None
    assert max(png_size(page.image)) <= PdfReader.MAX_IMAGE_SIDE


def test_nul_characters_are_removed() -> None:
    class Textpage:
        def get_text_range(self) -> str:
            return "Invoice\x00 number 1042 total due 250.00"

        def close(self) -> None: ...

    class Page:
        def get_textpage(self) -> Textpage:
            return Textpage()

    content = PdfReader._read_page(Page(), 1)

    assert content.text == "Invoice number 1042 total due 250.00"


def test_encrypted_pdf_is_reported(tmp_path: Path) -> None:
    with pytest.raises(PdfError) as caught:
        PdfReader(write(tmp_path, samples.encrypted_pdf())).page_count()
    assert caught.value.code == "pdf_encrypted"


def test_truncated_pdf_is_reported_as_corrupt(tmp_path: Path) -> None:
    with pytest.raises(PdfError) as caught:
        PdfReader(write(tmp_path, samples.corrupt_pdf())).page_count()
    assert caught.value.code == "pdf_corrupt"


def test_pdf_without_pages_is_reported_as_empty(tmp_path: Path) -> None:
    # PDFium itself refuses page-less files, so the "opened with zero pages" branch is
    # exercised with a stand-in document.
    empty = type("Empty", (), {"__len__": lambda s: 0, "close": lambda s: None})()
    with patch("pypdfium2.PdfDocument", return_value=empty):
        with pytest.raises(PdfError) as caught:
            PdfReader(tmp_path / "x.pdf").page_count()
    assert caught.value.code == "pdf_empty"


def test_real_pdf_with_an_empty_page_tree_is_rejected_by_pdfium(tmp_path: Path) -> None:
    # Pins current PDFium behaviour: it will not open a page-less file, so a real one is
    # reported as corrupt rather than empty. If a PDFium upgrade changes this, revisit D9.
    with pytest.raises(PdfError) as caught:
        PdfReader(write(tmp_path, samples.empty_pdf())).page_count()
    assert caught.value.code == "pdf_corrupt"


def test_pages_are_produced_lazily(tmp_path: Path) -> None:
    pages = PdfReader(write(tmp_path, samples.text_pdf(50))).pages()

    first = next(pages)

    assert first.page_no == 1  # the other 49 pages have not been read yet
    pages.close()
