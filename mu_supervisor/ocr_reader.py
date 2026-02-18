"""OCR reader: extract level and experience numbers from game screenshots."""

from __future__ import annotations

import logging
import re
from typing import Optional

import cv2
import numpy as np
import pytesseract

from .config import Config, OcrRegions
from .constants import (
    DEFAULT_HSV_LOWER,
    DEFAULT_HSV_UPPER,
    OCR_CHAR_FIXES,
    OCR_FAILURE_THRESHOLD,
    PSM_SINGLE_LINE,
)
from .exceptions import OCRError
from .window_manager import WindowManager

logger = logging.getLogger("mu_supervisor")


class OcrReader:
    """Read numeric values from the MU Online UI using HSV filtering + Tesseract."""

    def __init__(self, config: Config) -> None:
        pytesseract.pytesseract.tesseract_cmd = config.tesseract_path
        self._regions: OcrRegions = config.ocr_regions
        self._consecutive_failures: int = 0

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures

    def reset_failures(self) -> None:
        self._consecutive_failures = 0

    # ------------------------------------------------------------------
    # Image pre-processing
    # ------------------------------------------------------------------

    @staticmethod
    def filter_golden_text(image: np.ndarray) -> np.ndarray:
        """Isolate golden text from a BGR image via HSV filtering.

        Returns an inverted binary image (dark text on white background)
        suitable for Tesseract.
        """
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        lower = np.array(DEFAULT_HSV_LOWER, dtype=np.uint8)
        upper = np.array(DEFAULT_HSV_UPPER, dtype=np.uint8)
        mask = cv2.inRange(hsv, lower, upper)
        return cv2.bitwise_not(mask)

    # ------------------------------------------------------------------
    # OCR core
    # ------------------------------------------------------------------

    @staticmethod
    def extract_number(image: np.ndarray) -> Optional[int]:
        """Run Tesseract on a pre-processed image and return an integer.

        Applies character fixes from OCR_CHAR_FIXES and strips non-digit chars.
        Returns None if no valid number could be extracted.
        """
        custom_config = (
            f"--psm {PSM_SINGLE_LINE} "
            "-c tessedit_char_whitelist=0123456789OoQDIl|iSsBbGgZzTA"
        )
        raw = pytesseract.image_to_string(image, config=custom_config).strip()

        if not raw:
            return None

        fixed = "".join(OCR_CHAR_FIXES.get(ch, ch) for ch in raw)
        digits = re.sub(r"\D", "", fixed)

        if not digits:
            return None

        return int(digits)

    # ------------------------------------------------------------------
    # High-level readers
    # ------------------------------------------------------------------

    def read_level(self, wm: WindowManager) -> Optional[int]:
        """Capture the level region and return the current level."""
        return self._read_region(wm, self._regions.level, "level")

    def read_experience(self, wm: WindowManager) -> Optional[int]:
        """Capture the experience region and return the current experience."""
        return self._read_region(wm, self._regions.experience, "experience")

    def _read_region(self, wm: WindowManager, region, label: str) -> Optional[int]:
        try:
            raw_img = wm.capture_region(region)
            filtered = self.filter_golden_text(raw_img)
            value = self.extract_number(filtered)

            if value is None:
                self._consecutive_failures += 1
                logger.warning(
                    "OCR failed for %s (%d/%d consecutive failures)",
                    label, self._consecutive_failures, OCR_FAILURE_THRESHOLD,
                )
                if self._consecutive_failures >= OCR_FAILURE_THRESHOLD:
                    raise OCRError(
                        f"OCR failed {OCR_FAILURE_THRESHOLD} consecutive times for {label}"
                    )
                return None

            self._consecutive_failures = 0
            logger.debug("OCR %s = %d", label, value)
            return value

        except OCRError:
            raise
        except Exception as exc:
            self._consecutive_failures += 1
            logger.warning("OCR error reading %s: %s", label, exc)
            if self._consecutive_failures >= OCR_FAILURE_THRESHOLD:
                raise OCRError(
                    f"OCR failed {OCR_FAILURE_THRESHOLD} consecutive times for {label}"
                ) from exc
            return None
