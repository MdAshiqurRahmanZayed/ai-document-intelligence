"""Reads an image file (JPG, PNG, TIFF) frame by frame. Pure: no database or storage imports."""

import io
from collections.abc import Generator, Iterator
from contextlib import contextmanager
from pathlib import Path

from PIL import Image, ImageOps

from app.pipeline.pdf import PageContent, PdfReader


class ImageError(Exception):
    """The image cannot be decoded. `code` is stored on the document and shown to the user."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class ImageReader:
    """Turns each frame of one image file into a PNG page image."""

    # Same cap as scanned PDF pages, so OCR sees one size range whatever the source.
    MAX_IMAGE_SIDE = PdfReader.MAX_IMAGE_SIDE

    def __init__(self, path: Path) -> None:
        self.path = path

    def page_count(self) -> int:
        with self._decoding():
            with Image.open(self.path) as image:
                return int(getattr(image, "n_frames", 1))

    def pages(self) -> Generator[PageContent]:
        """Yield frames lazily so only one decoded frame is in memory at a time."""
        with self._decoding():
            image = Image.open(self.path)
            frames = int(getattr(image, "n_frames", 1))
        with image:
            for number in range(1, frames + 1):
                with self._decoding():
                    image.seek(number - 1)
                    png = self._to_png(image)
                yield PageContent(number, None, png)

    @staticmethod
    @contextmanager
    def _decoding() -> Iterator[None]:
        # Pillow decodes lazily, so a truncated file often fails on load rather than on open.
        # Truncated-image tolerance stays off: a cut-off file should fail, not give a grey page.
        try:
            yield
        except (OSError, SyntaxError, ValueError, Image.DecompressionBombError) as exc:
            raise ImageError("image_corrupt") from exc

    @classmethod
    def _to_png(cls, frame: Image.Image) -> bytes:
        # Phones store photos sideways plus an EXIF flag; apply it so the page is upright.
        upright = ImageOps.exif_transpose(frame).convert("RGB")
        upright.thumbnail((cls.MAX_IMAGE_SIDE, cls.MAX_IMAGE_SIDE))  # shrinks only, keeps ratio
        buffer = io.BytesIO()
        upright.save(buffer, format="PNG")
        return buffer.getvalue()
