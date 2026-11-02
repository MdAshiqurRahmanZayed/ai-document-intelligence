import pytest

from app.pipeline.ocr import OcrEngine
from tests import image_samples as samples


def words(*entries: tuple[str, str, int]) -> dict[str, list[str]]:
    """Tesseract-style word table: (text, conf, line_no) per row, all in one block."""
    return {
        "text": [e[0] for e in entries],
        "conf": [e[1] for e in entries],
        "block_num": ["1"] * len(entries),
        "par_num": ["1"] * len(entries),
        "line_num": [str(e[2]) for e in entries],
    }


def test_confidence_is_the_mean_of_word_confidences_scaled_to_one() -> None:
    result = OcrEngine._summarise(words(("Total", "90", 1), ("250.00", "70", 1), ("Paid", "80", 2)))

    assert result.text == "Total 250.00\nPaid"
    assert result.confidence == pytest.approx(0.8)


def test_non_word_rows_are_ignored_and_no_words_means_no_confidence() -> None:
    rows = words(("", "-1", 0), (" ", "95", 1), ("Total", "60", 1))
    assert OcrEngine._summarise(rows).confidence == pytest.approx(0.6)

    blank = OcrEngine._summarise(words(("", "-1", 0)))
    assert (blank.text, blank.confidence) == ("", None)


def test_clean_image_is_read_with_high_confidence() -> None:
    result = OcrEngine().read(samples.encode(samples.text_image()))

    assert "INVOICE" in result.text and "1042" in result.text
    assert result.confidence is not None and result.confidence > 0.8


def test_skewed_and_noisy_images_are_still_read() -> None:
    engine = OcrEngine()

    skewed = engine.read(samples.encode(samples.skewed(samples.text_image(), 5)))
    noisy = engine.read(samples.encode(samples.noisy(samples.text_image())))

    assert "INVOICE" in skewed.text and "1042" in skewed.text
    assert "INVOICE" in noisy.text and "1042" in noisy.text


def test_blank_page_gives_empty_text_without_failing() -> None:
    result = OcrEngine().read(samples.encode(samples.blank_image()))

    assert (result.text, result.confidence) == ("", None)


def test_undecodable_png_raises() -> None:
    with pytest.raises(ValueError):
        OcrEngine().read(b"not a png")
