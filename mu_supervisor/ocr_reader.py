"""OCR reader: extract level and experience numbers from game screenshots."""

from __future__ import annotations

import logging
import re
from typing import Optional, Tuple

import cv2
import numpy as np
import pytesseract

from .config import Config, OcrRegions, Region
from .constants import (
    DEFAULT_HSV_LOWER,
    DEFAULT_HSV_UPPER,
    NAVIGATION_COORD_PATTERN,
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
        self._coords_region: Region | None = (
            config.navigation.coords_region if config.navigation else None
        )
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
        """Read level from window title. Falls back to OCR if not found."""
        level = self._read_level_from_title(wm)
        if level is not None:
            self._consecutive_failures = 0
            return level
        return self._read_region(wm, self._regions.level, "level")

    @staticmethod
    def _read_level_from_title(wm: WindowManager) -> Optional[int]:
        """Parse level from window title like 'Level: [400]'."""
        title = wm.get_window_title()
        if not title:
            return None
        match = re.search(r"Level:\s*\[(\d+)\]", title)
        if not match:
            return None
        level = int(match.group(1))
        logger.debug("Level from title: %d", level)
        return level

    def read_experience(self, wm: WindowManager) -> Optional[int]:
        """Capture the experience region and return the current experience."""
        return self._read_region(wm, self._regions.experience, "experience")

    def read_coordinates(self, wm: "WindowManager") -> Optional[Tuple[int, int]]:
        """Capture the coordinate region and parse X, Y game coordinates.

        Returns (x, y) or None if parsing fails.
        """
        if self._coords_region is None:
            logger.warning("No coords_region configured — cannot read coordinates")
            return None

        try:
            raw_img = wm.capture_region(self._coords_region)

            # Scale up 3x for better OCR on small text
            h, w = raw_img.shape[:2]
            raw_img = cv2.resize(raw_img, (w * 3, h * 3), interpolation=cv2.INTER_CUBIC)

            # Try golden-text filter first, fall back to simple threshold
            filtered = self.filter_golden_text(raw_img)
            text = self._ocr_text(filtered)

            if not text:
                gray = cv2.cvtColor(raw_img, cv2.COLOR_BGR2GRAY)
                _, filtered = cv2.threshold(gray, 128, 255, cv2.THRESH_BINARY)
                text = self._ocr_text(filtered)

            if not text:
                logger.debug("read_coordinates: OCR returned empty text")
                return None

            # Apply char fixes then search for two digit groups
            fixed = "".join(OCR_CHAR_FIXES.get(ch, ch) for ch in text)
            match = re.search(NAVIGATION_COORD_PATTERN, fixed)
            if not match:
                logger.debug("read_coordinates: no coordinate pattern in %r", text)
                return None

            x, y = int(match.group(1)), int(match.group(2))
            logger.debug("read_coordinates: (%d, %d)", x, y)
            return (x, y)

        except Exception as exc:
            logger.warning("read_coordinates failed: %s", exc)
            return None

    @staticmethod
    def _ocr_text(image: np.ndarray) -> str:
        """Run Tesseract on a pre-processed image and return raw text."""
        custom_config = (
            f"--psm {PSM_SINGLE_LINE} "
            "-c tessedit_char_whitelist=0123456789OoQDIl|iSsBbGgZzTA,: "
        )
        return pytesseract.image_to_string(image, config=custom_config).strip()

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
