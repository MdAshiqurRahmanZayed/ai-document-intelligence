"""Builds test images in memory so no binary fixtures are committed."""

import io

import numpy as np
from PIL import Image, ImageDraw, ImageFont

# Big, plain type so Tesseract reads it reliably; the tests are about our code, not its accuracy.
TEXT = "INVOICE 1042 TOTAL 250.00"


def text_image(text: str = TEXT, size: tuple[int, int] = (1400, 300)) -> Image.Image:
    image = Image.new("RGB", size, "white")
    font = ImageFont.load_default(size=90)
    ImageDraw.Draw(image).text((40, 90), text, fill="black", font=font)
    return image


def blank_image() -> Image.Image:
    return Image.new("RGB", (800, 300), "white")


def skewed(image: Image.Image, degrees: float) -> Image.Image:
    return image.rotate(degrees, expand=True, fillcolor="white", resample=Image.Resampling.BICUBIC)


def noisy(image: Image.Image, strength: float = 25.0) -> Image.Image:
    pixels = np.asarray(image, dtype=np.float32)
    noise = np.random.default_rng(0).normal(0, strength, pixels.shape)
    return Image.fromarray(np.clip(pixels + noise, 0, 255).astype(np.uint8))


def encode(image: Image.Image, fmt: str = "PNG", **options: object) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format=fmt, **options)
    return buffer.getvalue()


def tiff(frames: list[Image.Image]) -> bytes:
    return encode(frames[0], "TIFF", save_all=True, append_images=frames[1:])


def exif_rotated_jpeg(upright: Image.Image) -> bytes:
    """A phone-style photo: pixels stored sideways, EXIF orientation 6 says how to turn it."""
    exif = Image.Exif()
    exif[0x0112] = 6
    return encode(upright.rotate(90, expand=True), "JPEG", exif=exif)


def truncated(data: bytes) -> bytes:
    return data[: len(data) // 2]
