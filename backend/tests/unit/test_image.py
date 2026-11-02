import io
from pathlib import Path

import pytest
from PIL import Image

from app.pipeline.image import ImageError, ImageReader
from tests import image_samples as samples


def write(tmp_path: Path, content: bytes) -> Path:
    path = tmp_path / "image.bin"
    path.write_bytes(content)
    return path


def size(png: bytes | None) -> tuple[int, int]:
    assert png is not None
    return Image.open(io.BytesIO(png)).size


@pytest.mark.parametrize("fmt", ["JPEG", "PNG"])
def test_single_image_is_one_png_page(tmp_path: Path, fmt: str) -> None:
    reader = ImageReader(write(tmp_path, samples.encode(samples.text_image(), fmt)))

    (page,) = reader.pages()

    assert reader.page_count() == 1
    assert page.page_no == 1 and page.text is None
    assert page.image is not None and page.image.startswith(b"\x89PNG")


def test_multi_frame_tiff_gives_one_page_per_frame(tmp_path: Path) -> None:
    reader = ImageReader(write(tmp_path, samples.tiff([samples.text_image()] * 3)))

    pages = list(reader.pages())

    assert reader.page_count() == 3
    assert [p.page_no for p in pages] == [1, 2, 3]


def test_exif_rotated_photo_comes_out_upright(tmp_path: Path) -> None:
    upright = samples.text_image()  # wide: 1400 x 300

    (page,) = ImageReader(write(tmp_path, samples.exif_rotated_jpeg(upright))).pages()

    assert size(page.image) == upright.size


def test_oversized_image_is_scaled_down_and_small_one_is_not_enlarged(tmp_path: Path) -> None:
    big = Image.new("RGB", (6000, 3000), "white")
    (scaled,) = ImageReader(write(tmp_path, samples.encode(big))).pages()
    (small,) = ImageReader(write(tmp_path, samples.encode(samples.text_image()))).pages()

    assert size(scaled.image) == (ImageReader.MAX_IMAGE_SIDE, 2500)
    assert size(small.image) == samples.text_image().size


@pytest.mark.parametrize(
    "content",
    [samples.truncated(samples.encode(samples.text_image(), "JPEG")), b"not an image at all"],
)
def test_undecodable_data_is_reported_as_corrupt(tmp_path: Path, content: bytes) -> None:
    with pytest.raises(ImageError) as caught:
        list(ImageReader(write(tmp_path, content)).pages())
    assert caught.value.code == "image_corrupt"


def test_frames_are_produced_lazily(tmp_path: Path) -> None:
    pages = ImageReader(write(tmp_path, samples.tiff([samples.text_image()] * 5))).pages()

    assert next(pages).page_no == 1  # the other frames have not been decoded yet
    pages.close()
