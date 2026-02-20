"""Main supervisor loop: state machine that monitors and manages the game."""

from __future__ import annotations

import enum
import logging
import re
import time

import pyautogui
import pydirectinput

from .config import Config, FarmingSpot
from .constants import (
    FARM_CHECK_INTERVAL,
    HELPER_RETRY_TIMEOUT,
    HELPER_STUCK_TIMEOUT,
    LAUNCH_FAILURE_PAUSE_SECONDS,
    OCR_FAILURE_PAUSE_SECONDS,
    POST_RECONNECT_DELAY,
    RESET_DISCONNECT_DELAY,
    WARP_TRAVEL_DELAY,
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
        self._popup_dismissed = False

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
            self._popup_dismissed = False
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

            # Execute post-login steps (e.g. select skill)
            self._run_post_login_steps()

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
            # 0. Check if we're already on the right map (save zen on warp)
            already_at_spot = False
            location_text = self._ocr.read_location_text(self._wm)
            if location_text and spot.name.lower() in location_text.lower():
                logger.info(
                    "Already at %s (read: %r) — skipping warp",
                    spot.name, location_text,
                )
                already_at_spot = True

            # 1. Warp to map if needed
            if not already_at_spot:
                if spot.warp_command is not None:
                    logger.info("Warping to %s via command: %s", spot.name, spot.warp_command)
                    send_chat_command(spot.warp_command, self._wm)
                    time.sleep(WARP_TRAVEL_DELAY)
                elif spot.warp_button is not None:
                    logger.info("Warping to %s via M menu", spot.name)
                    self._navigator.warp_to(self._wm, spot.warp_button)

            # 1.5. Verify warp succeeded
            if not already_at_spot and (spot.warp_command or spot.warp_button):
                location_text = self._ocr.read_location_text(self._wm)
                # Strip trailing digits from spot name for comparison:
                # "Elveland3" → "Elveland", "Aida1" → "Aida", "LostTower6" → "LostTower"
                map_base = re.sub(r"\d+$", "", spot.name).lower()
                if not location_text or map_base not in location_text.lower():
                    logger.warning(
                        "Warp to %s failed (location: %r) — will retry",
                        spot.name, location_text,
                    )
                    self._state = State.READ_STATUS
                    return

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

            # 3. Farm at the spot (small delay for map to finish loading)
            time.sleep(2)
            if spot.farm_action == "hold_right_click":
                self._farm_hold_right_click(spot)
            elif spot.farm_action == "middle_click":
                if not self._farm_middle_click(spot):
                    # Stagnation — stay in NAVIGATE_AND_FARM to re-warp
                    return

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
        """Send /reset and optionally wait for disconnect + reconnect."""
        try:
            logger.info("Sending /reset command")
            send_chat_command("/reset", self._wm)

            if self._config.reset_needs_reconnect:
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
            self._popup_dismissed = False
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
    # Post-login setup
    # ------------------------------------------------------------------

    def _run_post_login_steps(self) -> None:
        """Execute post-login clicks (e.g. select skill from bar)."""
        steps = self._config.post_login_steps
        if not steps:
            return

        logger.info("Running %d post-login step(s)", len(steps))
        self._wm.focus_window()

        for step in steps:
            logger.info("Post-login: %s at (%d, %d)", step.label, step.point.x, step.point.y)
            pyautogui.moveTo(step.point.x, step.point.y)
            pyautogui.mouseDown()
            time.sleep(0.2)
            pyautogui.mouseUp()
            if step.wait_after > 0:
                time.sleep(step.wait_after)

        logger.info("Post-login steps complete")

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
                self._check_level_up_popup(level)
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

    def _check_level_up_popup(self, level: int) -> None:
        """Dismiss level-up popup by clicking screen center if level crossed threshold.

        Does NOT call focus_window() to avoid sending ALT during farming.
        Releases right-click briefly if held, clicks center, then re-presses.
        """
        threshold = self._config.level_up_dismiss
        if threshold is None or self._popup_dismissed:
            return
        if level > threshold:
            cx, cy = self._wm.get_window_center()
            logger.info("Level %d > %d — dismissing level-up popup", level, threshold)

            # Release right-click temporarily to avoid interference
            pyautogui.mouseUp(button="right")
            time.sleep(0.3)

            pyautogui.click(cx, cy)
            time.sleep(1.0)

            # Re-press right-click so farming continues
            pyautogui.moveTo(cx, cy)
            pyautogui.mouseDown(button="right")

            self._popup_dismissed = True

    def _activate_helper(self) -> None:
        """Activate MU Helper via helper_button click or middle click."""
        self._wm.focus_window()
        time.sleep(0.3)

        hb = self._config.helper_button
        if hb is not None:
            pyautogui.moveTo(hb.x, hb.y)
            time.sleep(0.15)
            pyautogui.mouseDown()
            time.sleep(0.2)
            pyautogui.mouseUp()
        else:
            cx, cy = self._wm.get_window_center()
            pyautogui.moveTo(cx, cy)
            time.sleep(0.15)
            pyautogui.mouseDown(button="middle")
            time.sleep(0.05)
            pyautogui.mouseUp(button="middle")

    def _farm_middle_click(self, spot: FarmingSpot) -> bool:
        """Middle-click to activate MU Helper and wait until reaching the spot's level.

        Returns True if the spot's target level was reached, False if stagnation
        was detected (caller should re-navigate).
        """
        # Mark popup as handled so the farming loop's _check_level_up_popup
        # won't left-click center and accidentally close MU Helper.
        if not self._popup_dismissed and self._config.level_up_dismiss is not None:
            if self._current_level and self._current_level > self._config.level_up_dismiss:
                logger.info("Skipping popup dismiss (will be handled by MU Helper)")
                self._popup_dismissed = True

        # Extra settle time — game may not accept middle click right after
        # warp/navigation until it finishes loading.
        time.sleep(3)
        self._activate_helper()
        logger.info(
            "Activated MU Helper at %s — farming until level %d",
            spot.name, spot.until_level,
        )

        last_level: int | None = None
        last_level_change_time = time.monotonic()
        helper_retried = False

        while True:
            time.sleep(FARM_CHECK_INTERVAL)

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
            self._check_level_up_popup(level)
            now = time.monotonic()

            # Track level changes
            if last_level is None or level != last_level:
                last_level = level
                last_level_change_time = now
                helper_retried = False

            stagnation = now - last_level_change_time

            logger.info(
                "Farming at %s (MU Helper) — level %d / %d (stale %.0fs)",
                spot.name, level, spot.until_level, stagnation,
            )

            # Stagnation: re-enable MU Helper once
            if stagnation >= HELPER_RETRY_TIMEOUT and not helper_retried:
                logger.warning(
                    "Level stagnant for %.0fs — re-enabling MU Helper",
                    stagnation,
                )
                self._activate_helper()
                helper_retried = True

            # Stagnation: give up and re-navigate
            if stagnation >= HELPER_STUCK_TIMEOUT:
                logger.warning(
                    "Level stagnant for %.0fs — assuming stuck/dead, re-navigating",
                    stagnation,
                )
                return False

            # Distribute stats while helper is active (chat doesn't interrupt it)
            if self._stats.should_distribute(level):
                try:
                    self._stats.distribute(level, self._wm)
                except DistributionError:
                    logger.warning("Stat distribution failed during farming", exc_info=True)

            if level >= spot.until_level:
                logger.info("Reached level %d — leaving %s", level, spot.name)
                return True
