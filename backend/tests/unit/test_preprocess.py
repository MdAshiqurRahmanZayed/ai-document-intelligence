import cv2
import numpy as np
import pytest

from app.pipeline.preprocess import Preprocessor
from tests import image_samples as samples


def gray(image: object) -> np.ndarray:
    return cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2GRAY)


def test_output_is_single_channel_black_and_white() -> None:
    cleaned = Preprocessor().clean(gray(samples.text_image()))

    assert cleaned.ndim == 2
    assert set(np.unique(cleaned)) <= {0, 255}


@pytest.mark.parametrize("degrees", [-6, 4])
def test_skewed_page_is_straightened_to_within_one_degree(degrees: float) -> None:
    pre = Preprocessor()
    tilted = gray(samples.skewed(samples.text_image(), degrees))

    assert abs(pre.tilt(tilted) + degrees) <= 1  # estimate undoes the skew
    assert abs(pre.tilt(pre.clean(tilted))) <= 1  # and the cleaned page is level


def test_straight_and_blank_pages_are_left_alone() -> None:
    pre = Preprocessor()

    assert pre.tilt(gray(samples.text_image())) == 0
    assert pre.tilt(gray(samples.blank_image())) == 0


def test_noisy_page_still_has_dark_text_pixels() -> None:
    cleaned = Preprocessor().clean(gray(samples.noisy(samples.text_image())))

    dark = (cleaned == 0).mean()
    assert 0.01 < dark < 0.3  # text survives, and the noise did not turn the page black
