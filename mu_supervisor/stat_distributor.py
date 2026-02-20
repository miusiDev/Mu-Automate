"""Stat point distribution via in-game chat commands."""

from __future__ import annotations

import logging
import math
import re
import time

import cv2
import pyautogui
import pyperclip
import pydirectinput
import pytesseract

from .config import Config, Region
from .constants import (
    CHAT_OPEN_DELAY,
    COMMAND_SEND_DELAY,
    MAX_POINTS_PER_COMMAND,
    PSM_SINGLE_LINE,
    STAT_COMMANDS,
)
from .exceptions import DistributionError
from .window_manager import WindowManager

logger = logging.getLogger("mu_supervisor")


class StatDistributor:
    """Distribute accumulated stat points based on config ratios."""

    def __init__(self, config: Config) -> None:
        self._interval = config.stats.interval_levels
        self._points_per_level = config.stats.points_per_level
        self._distribution = config.stats.distribution
        self._reset_level = config.reset_level
        self._points_region: Region | None = config.stats.points_region
        self._tesseract_path = config.tesseract_path
        self._stat_commands = config.stats.stat_commands or STAT_COMMANDS
        self._last_distributed_level: int = 0

    @property
    def last_distributed_level(self) -> int:
        return self._last_distributed_level

    def initialize_from_level(self, current_level: int) -> None:
        """Set the baseline so we don't re-distribute for past levels.

        Called once at startup: assumes all stats up to the current level
        have already been distributed (idempotent start).
        """
        self._last_distributed_level = (
            current_level // self._interval
        ) * self._interval
        logger.info(
            "Stat distributor initialized: baseline level=%d (current=%d)",
            self._last_distributed_level, current_level,
        )

    def should_distribute(self, current_level: int) -> bool:
        """Return True if enough levels have passed since last distribution."""
        return (current_level - self._last_distributed_level) >= self._interval

    def distribute(self, current_level: int, wm: WindowManager) -> None:
        """Read available points from character screen and send stat-add commands."""
        total_points = self._read_available_points(wm)

        if total_points <= 0:
            logger.info("No stat points to distribute")
            self._last_distributed_level = current_level
            return

        wm.focus_window()

        for stat_key, ratio in self._distribution.items():
            if ratio <= 0:
                continue

            points = int(total_points * ratio)
            if points <= 0:
                continue

            command = self._stat_commands.get(stat_key)
            if command is None:
                logger.warning("Unknown stat key %r, skipping", stat_key)
                continue

            self._send_stat_points(command, points, wm)

        self._last_distributed_level = current_level
        logger.info(
            "Stat distribution complete. Baseline updated to level %d",
            current_level,
        )

    def distribute_for_reset(self, wm: WindowManager) -> None:
        """Distribute all stat points after a reset (character at level 1).

        Reads available points from the character screen (C key) and waits
        2 seconds between each /add command.
        """
        total_points = self._read_available_points(wm)

        if total_points <= 0:
            logger.info("No stat points to distribute")
            return

        wm.focus_window()

        first = True
        for stat_key, ratio in self._distribution.items():
            if ratio <= 0:
                continue

            points = int(total_points * ratio)
            if points <= 0:
                continue

            command = self._stat_commands.get(stat_key)
            if command is None:
                logger.warning("Unknown stat key %r, skipping", stat_key)
                continue

            if not first:
                time.sleep(2.0)
            first = False

            self._send_stat_points(command, points, wm)

        logger.info("Post-reset distribution complete")

    def _read_available_points(self, wm: WindowManager) -> int:
        """Open character screen (C), OCR the points region, close (C).

        Returns the number of available stat points.
        """
        wm.focus_window()

        # Open character screen
        pydirectinput.press("c")
        time.sleep(0.5)

        try:
            raw_img = wm.capture_region(self._points_region)

            # Scale up for better OCR
            h, w = raw_img.shape[:2]
            raw_img = cv2.resize(raw_img, (w * 3, h * 3), interpolation=cv2.INTER_CUBIC)

            gray = cv2.cvtColor(raw_img, cv2.COLOR_BGR2GRAY)
            _, thresh = cv2.threshold(gray, 128, 255, cv2.THRESH_BINARY)

            pytesseract.pytesseract.tesseract_cmd = self._tesseract_path
            text = pytesseract.image_to_string(
                thresh,
                config=f"--psm {PSM_SINGLE_LINE} -c tessedit_char_whitelist=0123456789",
            ).strip()

            digits = re.sub(r"\D", "", text)
            points = int(digits) if digits else 0
            logger.info("Read available points from character screen: %d", points)
            return points
        finally:
            # Close character screen
            pydirectinput.press("c")
            time.sleep(0.3)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _send_stat_points(command: str, total: int, wm: WindowManager) -> None:
        """Send one or more /add commands, chunked to MAX_POINTS_PER_COMMAND."""
        remaining = total
        while remaining > 0:
            chunk = min(remaining, MAX_POINTS_PER_COMMAND)
            full_cmd = f"{command} {chunk}"

            logger.debug("Sending: %s", full_cmd)
            send_chat_command(full_cmd, wm)
            remaining -= chunk

        logger.info("Sent %s: %d total points", command, total)


def send_chat_command(text: str, wm: WindowManager) -> None:
    """Open chat, paste the command via clipboard, and press Enter."""
    wm.focus_window()

    # Open chat
    pydirectinput.press("enter")
    time.sleep(CHAT_OPEN_DELAY)

    # Copy to clipboard right before pasting to avoid anything overwriting it
    pyperclip.copy(text)
    time.sleep(0.1)

    # Paste via clipboard — use pyautogui.hotkey for reliable Ctrl+V
    # (pydirectinput keyDown/press combo drops Ctrl in DirectX games, sending bare "V" which opens inventory)
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.3)

    # Send
    pydirectinput.press("enter")
    time.sleep(COMMAND_SEND_DELAY)
