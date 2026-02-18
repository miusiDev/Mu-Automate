"""Stat point distribution via in-game chat commands."""

from __future__ import annotations

import logging
import math
import time

import pyperclip
import pydirectinput

from .config import Config
from .constants import (
    CHAT_OPEN_DELAY,
    COMMAND_SEND_DELAY,
    MAX_POINTS_PER_COMMAND,
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
        """Calculate and send stat-add commands for the accumulated levels."""
        levels_gained = current_level - self._last_distributed_level
        total_points = levels_gained * self._points_per_level

        logger.info(
            "Distributing stats: %d levels gained × %d pts = %d total points",
            levels_gained, self._points_per_level, total_points,
        )

        wm.focus_window()

        for stat_key, ratio in self._distribution.items():
            if ratio <= 0:
                continue

            points = int(total_points * ratio)
            if points <= 0:
                continue

            command = STAT_COMMANDS.get(stat_key)
            if command is None:
                logger.warning("Unknown stat key %r, skipping", stat_key)
                continue

            self._send_stat_points(command, points, wm)

        self._last_distributed_level = current_level
        logger.info(
            "Stat distribution complete. Baseline updated to level %d",
            current_level,
        )

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
            _send_chat_command(full_cmd, wm)
            remaining -= chunk

        logger.info("Sent %s: %d total points", command, total)


def _send_chat_command(text: str, wm: WindowManager) -> None:
    """Open chat, paste the command via clipboard, and press Enter."""
    wm.focus_window()

    # Open chat
    pydirectinput.press("enter")
    time.sleep(CHAT_OPEN_DELAY)

    # Paste via clipboard (avoids pydirectinput issues with / on non-US layouts)
    pyperclip.copy(text)
    pydirectinput.keyDown("ctrl")
    pydirectinput.press("v")
    pydirectinput.keyUp("ctrl")
    time.sleep(0.1)

    # Send
    pydirectinput.press("enter")
    time.sleep(COMMAND_SEND_DELAY)
