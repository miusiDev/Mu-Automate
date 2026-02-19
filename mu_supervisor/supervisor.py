"""Main supervisor loop: state machine that monitors and manages the game."""

from __future__ import annotations

import enum
import logging
import time

import pyautogui

from .config import Config, FarmingSpot
from .constants import (
    LAUNCH_FAILURE_PAUSE_SECONDS,
    OCR_FAILURE_PAUSE_SECONDS,
    POST_RECONNECT_DELAY,
    RESET_DISCONNECT_DELAY,
)
from .exceptions import (
    DistributionError,
    GameWindowError,
    LaunchError,
    OCRError,
)
from .game_launcher import GameLauncher
from .navigator import Navigator
from .ocr_reader import OcrReader
from .stat_distributor import StatDistributor, send_chat_command
from .window_manager import WindowManager

logger = logging.getLogger("mu_supervisor")


class State(enum.Enum):
    CHECK_GAME_ALIVE = "CHECK_GAME_ALIVE"
    LAUNCH_GAME = "LAUNCH_GAME"
    READ_STATUS = "READ_STATUS"
    NAVIGATE_AND_FARM = "NAVIGATE_AND_FARM"
    DISTRIBUTE_STATS = "DISTRIBUTE_STATS"
    RESET = "RESET"
    WAIT = "WAIT"
    ERROR_PAUSE = "ERROR_PAUSE"


class Supervisor:
    """Top-level state machine that ties all modules together.

    Flow:
        CHECK_GAME_ALIVE → [not alive] → LAUNCH_GAME → CHECK_GAME_ALIVE
                         → [alive]     → READ_STATUS
        READ_STATUS → [active spot] → NAVIGATE_AND_FARM → READ_STATUS
                    → [level >= reset_level] → RESET → CHECK_GAME_ALIVE
                    → [should distribute] → DISTRIBUTE_STATS → WAIT
                    → [else] → WAIT
        WAIT (sleep N seconds) → CHECK_GAME_ALIVE
        Any exception → ERROR_PAUSE → CHECK_GAME_ALIVE
    """

    def __init__(self, config: Config) -> None:
        self._config = config
        self._wm = WindowManager(config.window_title)
        self._ocr = OcrReader(config)
        self._stats = StatDistributor(config)
        self._launcher = GameLauncher(config, self._wm)
        self._navigator: Navigator | None = (
            Navigator(config, self._ocr) if config.navigation else None
        )

        self._state = State.CHECK_GAME_ALIVE
        self._error_pause_seconds: float = 0
        self._initialized = False
        self._current_level: int | None = None

    def run(self) -> None:
        """Run the supervisor loop indefinitely."""
        logger.info("Supervisor started — loop interval=%ds", self._config.loop_interval_seconds)

        while True:
            try:
                self._tick()
            except KeyboardInterrupt:
                logger.info("Supervisor stopped by user (Ctrl+C)")
                break
            except Exception:
                logger.critical("Unexpected error in supervisor loop", exc_info=True)
                self._state = State.ERROR_PAUSE
                self._error_pause_seconds = 60

    # ------------------------------------------------------------------
    # State machine
    # ------------------------------------------------------------------

    def _tick(self) -> None:
        logger.debug("State: %s", self._state.value)

        if self._state == State.CHECK_GAME_ALIVE:
            self._do_check_game_alive()
        elif self._state == State.LAUNCH_GAME:
            self._do_launch_game()
        elif self._state == State.READ_STATUS:
            self._do_read_status()
        elif self._state == State.NAVIGATE_AND_FARM:
            self._do_navigate_and_farm()
        elif self._state == State.DISTRIBUTE_STATS:
            self._do_distribute_stats()
        elif self._state == State.RESET:
            self._do_reset()
        elif self._state == State.WAIT:
            self._do_wait()
        elif self._state == State.ERROR_PAUSE:
            self._do_error_pause()

    # -- Individual state handlers --

    def _do_check_game_alive(self) -> None:
        if self._launcher.is_game_running():
            logger.debug("Game window is alive")
            self._state = State.READ_STATUS
        else:
            logger.warning("Game window not found — will attempt relaunch")
            self._state = State.LAUNCH_GAME

    def _do_launch_game(self) -> None:
        try:
            self._launcher.launch_and_login()
            self._initialized = False
            self._state = State.CHECK_GAME_ALIVE
        except LaunchError as exc:
            logger.error("Launch failed: %s", exc)
            self._state = State.ERROR_PAUSE
            self._error_pause_seconds = LAUNCH_FAILURE_PAUSE_SECONDS

    def _do_read_status(self) -> None:
        try:
            level = self._ocr.read_level(self._wm)
        except OCRError as exc:
            logger.error("OCR failure: %s", exc)
            self._ocr.reset_failures()
            self._state = State.ERROR_PAUSE
            self._error_pause_seconds = OCR_FAILURE_PAUSE_SECONDS
            return
        except GameWindowError:
            self._state = State.CHECK_GAME_ALIVE
            return

        if level is None:
            self._state = State.WAIT
            return

        self._current_level = level

        # Initialize stat distributor baseline
        if not self._initialized:
            self._stats.initialize_from_level(level)
            self._initialized = True

            # After reset (or fresh start at level 1), distribute all points
            if level <= 1:
                try:
                    self._stats.distribute_for_reset(self._wm)
                except (DistributionError, GameWindowError) as exc:
                    logger.error("Post-reset stat distribution failed: %s", exc)

        # Check for active farming spot
        active_spot = self._get_active_spot(level)
        if active_spot is not None and self._navigator is not None:
            logger.info(
                "Level %d — active spot: %s (until %d)",
                level, active_spot.name, active_spot.until_level,
            )
            self._state = State.NAVIGATE_AND_FARM
            return

        # Check reset level
        if level >= self._config.reset_level:
            logger.info(
                "Level %d >= reset level %d — resetting",
                level, self._config.reset_level,
            )
            self._state = State.RESET
            return

        # Check if we should distribute stats
        if self._stats.should_distribute(level):
            self._state = State.DISTRIBUTE_STATS
        else:
            self._state = State.WAIT

    def _do_navigate_and_farm(self) -> None:
        if self._navigator is None or self._current_level is None:
            self._state = State.WAIT
            return

        spot = self._get_active_spot(self._current_level)
        if spot is None:
            self._state = State.READ_STATUS
            return

        try:
            # 1. Warp to map if needed
            if spot.warp_button is not None:
                logger.info("Warping to %s", spot.name)
                self._navigator.warp_to(self._wm, spot.warp_button)

            # 2. Walk to spot if needed
            if spot.spot is not None:
                logger.info(
                    "Walking to %s spot (%d, %d)",
                    spot.name, spot.spot.x, spot.spot.y,
                )
                success = self._navigator.navigate_to(
                    self._wm, spot.spot, spot.waypoints,
                )
                if not success:
                    logger.error("Navigation to %s failed", spot.name)
                    self._state = State.ERROR_PAUSE
                    self._error_pause_seconds = 60
                    return

            # 3. Farm at the spot
            if spot.farm_action == "hold_right_click":
                self._farm_hold_right_click(spot)
            elif spot.farm_action == "middle_click":
                self._farm_middle_click(spot)

        except GameWindowError:
            self._state = State.CHECK_GAME_ALIVE
            return

        # Spot complete — re-read status to route to next spot or reset
        self._state = State.READ_STATUS

    def _do_distribute_stats(self) -> None:
        if self._current_level is None:
            self._state = State.WAIT
            return

        try:
            self._stats.distribute(self._current_level, self._wm)
        except (DistributionError, GameWindowError) as exc:
            logger.error("Stat distribution failed: %s", exc)
            self._state = State.ERROR_PAUSE
            self._error_pause_seconds = 60
            return

        self._state = State.WAIT

    def _do_reset(self) -> None:
        """Send /reset, wait for disconnect, and reconnect."""
        try:
            logger.info("Sending /reset command")
            send_chat_command("/reset", self._wm)

            logger.info("Waiting %ds for disconnect", RESET_DISCONNECT_DELAY)
            time.sleep(RESET_DISCONNECT_DELAY)

            # Click connect to re-enter the game
            lc = self._config.launcher
            logger.info(
                "Clicking Connect at (%d, %d)",
                lc.connect_button.x, lc.connect_button.y,
            )
            pyautogui.click(lc.connect_button.x, lc.connect_button.y)

            logger.info("Waiting %ds for reconnect", POST_RECONNECT_DELAY)
            time.sleep(POST_RECONNECT_DELAY)

            self._initialized = False
            self._state = State.CHECK_GAME_ALIVE

        except GameWindowError:
            self._state = State.CHECK_GAME_ALIVE

    def _do_wait(self) -> None:
        logger.debug("Waiting %ds before next cycle", self._config.loop_interval_seconds)
        time.sleep(self._config.loop_interval_seconds)
        self._state = State.CHECK_GAME_ALIVE

    def _do_error_pause(self) -> None:
        logger.info("Error pause: sleeping %ds before retry", self._error_pause_seconds)
        time.sleep(self._error_pause_seconds)
        self._state = State.CHECK_GAME_ALIVE

    # ------------------------------------------------------------------
    # Farming helpers
    # ------------------------------------------------------------------

    def _get_active_spot(self, level: int) -> FarmingSpot | None:
        """Return the farming spot for the current level, or None."""
        if self._config.navigation is None:
            return None
        for spot in self._config.navigation.spots:
            if level < spot.until_level:
                return spot
        return None

    def _farm_hold_right_click(self, spot: FarmingSpot) -> None:
        """Hold right-click at the current position until reaching the spot's level."""
        cx, cy = self._wm.get_window_center()
        self._wm.focus_window()
        pyautogui.moveTo(cx, cy)
        pyautogui.mouseDown(button="right")
        logger.info(
            "Farming at %s — holding right-click until level %d",
            spot.name, spot.until_level,
        )

        try:
            while True:
                time.sleep(self._config.loop_interval_seconds)

                if not self._wm.is_window_alive():
                    raise GameWindowError("Game window lost during farming")

                try:
                    level = self._ocr.read_level(self._wm)
                except OCRError:
                    self._ocr.reset_failures()
                    continue

                if level is None:
                    continue

                self._current_level = level
                logger.info(
                    "Farming at %s — level %d / %d",
                    spot.name, level, spot.until_level,
                )

                if level >= spot.until_level:
                    logger.info("Reached level %d — leaving %s", level, spot.name)
                    break
        finally:
            pyautogui.mouseUp(button="right")
            logger.info("Released right-click")

    def _farm_middle_click(self, spot: FarmingSpot) -> None:
        """Middle-click to activate MU Helper and wait until reaching the spot's level."""
        cx, cy = self._wm.get_window_center()
        self._wm.focus_window()
        pyautogui.moveTo(cx, cy)
        pyautogui.mouseDown(button="middle")
        time.sleep(0.2)
        pyautogui.mouseUp(button="middle")
        logger.info(
            "Activated MU Helper at %s — farming until level %d",
            spot.name, spot.until_level,
        )

        while True:
            time.sleep(self._config.loop_interval_seconds)

            if not self._wm.is_window_alive():
                raise GameWindowError("Game window lost during farming")

            try:
                level = self._ocr.read_level(self._wm)
            except OCRError:
                self._ocr.reset_failures()
                continue

            if level is None:
                continue

            self._current_level = level
            logger.info(
                "Farming at %s (MU Helper) — level %d / %d",
                spot.name, level, spot.until_level,
            )

            # Distribute stats while helper is active (chat doesn't interrupt it)
            if self._stats.should_distribute(level):
                try:
                    self._stats.distribute(level, self._wm)
                except DistributionError:
                    logger.warning("Stat distribution failed during farming", exc_info=True)

            if level >= spot.until_level:
                logger.info("Reached level %d — leaving %s", level, spot.name)
                break
