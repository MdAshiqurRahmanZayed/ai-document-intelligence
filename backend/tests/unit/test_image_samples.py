import io

import pytest
from PIL import Image

from tests import image_samples as samples


def test_samples_decode_as_intended() -> None:
    assert Image.open(io.BytesIO(samples.encode(samples.text_image(), "JPEG"))).format == "JPEG"
    frames = Image.open(io.BytesIO(samples.tiff([samples.text_image()] * 3)))
    assert getattr(frames, "n_frames", 1) == 3
    assert samples.skewed(samples.text_image(), 5).size[0] > samples.text_image().size[0]


def test_truncated_image_fails_to_decode() -> None:
    cut = samples.truncated(samples.encode(samples.text_image(), "JPEG"))

    with pytest.raises(OSError):
        Image.open(io.BytesIO(cut)).load()
