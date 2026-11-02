"""Cleans a page picture before OCR. Pure: numpy/OpenCV in, numpy out."""

import cv2
import numpy as np
from numpy.typing import NDArray

Gray = NDArray[np.uint8]


class Preprocessor:
    """Grayscale -> deskew -> denoise -> contrast -> threshold. Works on a copy; the stored
    page image is never touched."""

    # Tilts beyond this are more likely a wrong estimate (or a sideways page) than a real skew.
    MAX_TILT_DEGREES = 15
    TILT_STEP_DEGREES = 0.5  # also the smallest correction worth applying
    # The tilt search runs on a shrunken copy: the angle is the same, the cost is far lower.
    TILT_SEARCH_SIDE = 800
    # Black blobs smaller than this (in pixels) are leftover noise, not ink: the smallest real
    # marks, such as the dot of an "i" at scan resolution, are larger.
    MIN_INK_AREA = 12

    def clean(self, gray: Gray) -> Gray:
        straight = self._deskew(gray)
        # Median blur removes speckle; a light Gaussian then smooths the grain it leaves, which
        # the threshold below would otherwise turn into black dots.
        smooth = cv2.GaussianBlur(cv2.medianBlur(straight, 3), (3, 3), 0)
        # CLAHE evens out local contrast, which rescues faded receipts and uneven lighting.
        contrast = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(smooth)
        # Adaptive (per-neighbourhood) threshold copes with shadows that a single cut-off cannot.
        # A pixel must be 25 levels darker than its surroundings to count as ink.
        binary = cv2.adaptiveThreshold(
            contrast, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 51, 25
        )
        return self._despeckle(np.asarray(binary, dtype=np.uint8))

    def _despeckle(self, binary: Gray) -> Gray:
        # Even a few scattered black dots make Tesseract's page layout step find no text at all,
        # so tiny blobs are erased (turned white) before it sees the page.
        count, labels, stats, _ = cv2.connectedComponentsWithStats(255 - binary)
        keep = stats[:, cv2.CC_STAT_AREA] >= self.MIN_INK_AREA
        keep[0] = False  # label 0 is the white background
        return np.where(keep[labels], 0, 255).astype(np.uint8)

    def tilt(self, gray: Gray) -> float:
        """Degrees to rotate the page to make its text lines horizontal (0 when unsure).

        Text lines make the row sums of the dark pixels very uneven (lines vs gaps), and that
        unevenness is largest when the lines are exactly horizontal.
        """
        scale = self.TILT_SEARCH_SIDE / max(gray.shape)
        small = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        ink = cv2.threshold(small, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]

        def score(angle: float) -> float:
            h, w = ink.shape
            turn = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
            return float(np.var(cv2.warpAffine(ink, turn, (w, h)).sum(axis=1)))

        steps = int(self.MAX_TILT_DEGREES / self.TILT_STEP_DEGREES)
        angles = [i * self.TILT_STEP_DEGREES for i in range(-steps, steps + 1)]
        # On ties (a blank page scores the same everywhere) prefer the smallest turn.
        best = max(angles, key=lambda a: (score(a), -abs(a)))
        return 0.0 if abs(best) < self.TILT_STEP_DEGREES else best

    def _deskew(self, gray: Gray) -> Gray:
        angle = self.tilt(gray)
        if angle == 0:
            return gray
        h, w = gray.shape
        turn = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
        rotated = cv2.warpAffine(
            gray,
            turn,
            (w, h),
            flags=cv2.INTER_CUBIC,
            borderValue=255,  # new corners are white
        )
        return np.asarray(rotated, dtype=np.uint8)
