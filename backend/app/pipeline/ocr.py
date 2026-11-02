"""Reads the text of one page image with Tesseract. Pure: no database, storage or web imports."""

from dataclasses import dataclass

import cv2
import numpy as np
import pytesseract
from pytesseract import Output

from app.pipeline.preprocess import Preprocessor


@dataclass
class OcrResult:
    text: str  # empty for a blank page
    confidence: float | None  # 0 to 1; None when no words were recognised


class OcrEngine:
    # A hung Tesseract call must become an error the retry policy can handle, not a stuck worker.
    TIMEOUT_SECONDS = 120

    def __init__(self) -> None:
        self._preprocessor = Preprocessor()

    def read(self, png: bytes) -> OcrResult:
        decoded = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_GRAYSCALE)
        if decoded is None:
            raise ValueError("page image could not be decoded")
        gray = np.asarray(decoded, dtype=np.uint8)
        data = pytesseract.image_to_data(
            self._preprocessor.clean(gray), output_type=Output.DICT, timeout=self.TIMEOUT_SECONDS
        )
        return self._summarise(data)

    @staticmethod
    def _summarise(data: dict[str, list[str]]) -> OcrResult:
        lines: dict[tuple[str, str, str], list[str]] = {}
        confidences: list[float] = []
        for i, word in enumerate(data["text"]):
            confidence = float(data["conf"][i])
            # Tesseract reports -1 for layout rows that are not words.
            if confidence < 0 or not word.strip():
                continue
            key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
            lines.setdefault(key, []).append(word)
            confidences.append(confidence)
        if not confidences:
            return OcrResult("", None)
        text = "\n".join(" ".join(words) for words in lines.values())
        return OcrResult(text, sum(confidences) / len(confidences) / 100)
