"""Main supervisor loop: state machine that monitors and manages the game."""

from __future__ import annotations

import enum
import logging
import time

from .config import Config
from .constants import (
    LAUNCH_FAILURE_PAUSE_SECONDS,
    OCR_FAILURE_PAUSE_SECONDS,
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
from .stat_distributor import StatDistributor
from .window_manager import WindowManager

logger = logging.getLogger("mu_supervisor")


class State(enum.Enum):
    CHECK_GAME_ALIVE = "CHECK_GAME_ALIVE"
    LAUNCH_GAME = "LAUNCH_GAME"
    READ_STATUS = "READ_STATUS"
    NAVIGATE_TO_SPOT = "NAVIGATE_TO_SPOT"
    DISTRIBUTE_STATS = "DISTRIBUTE_STATS"
    WAIT = "WAIT"
    ERROR_PAUSE = "ERROR_PAUSE"


class Supervisor:
    """Top-level state machine that ties all modules together.

    Flow:
        CHECK_GAME_ALIVE → [not alive] → LAUNCH_GAME → CHECK_GAME_ALIVE
                         → [alive]     → READ_STATUS
        READ_STATUS → [level >= 400] → log + WAIT
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
        self._needs_navigation: bool = True

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
        elif self._state == State.NAVIGATE_TO_SPOT:
            self._do_navigate_to_spot()
        elif self._state == State.DISTRIBUTE_STATS:
            self._do_distribute_stats()
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
            self._initialized = False  # force re-init of stat baseline
            self._needs_navigation = True
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

        # Clear navigation flag once we're past low levels
        if level >= 30:
            self._needs_navigation = False

        # Low level navigation: walk to farming spot
        if level < 30 and self._needs_navigation and self._navigator is not None:
            logger.info("Level %d < 30 — navigating to farming spot", level)
            self._state = State.NAVIGATE_TO_SPOT
            return

        # One-time initialization of stat distributor baseline
        if not self._initialized:
            self._stats.initialize_from_level(level)
            self._initialized = True

        # Check reset level
        if level >= self._config.reset_level:
            logger.info(
                "Level %d >= reset level %d — web reset DEFERRED (not implemented)",
                level, self._config.reset_level,
            )
            self._state = State.WAIT
            return

        # Check if we should distribute stats
        if self._stats.should_distribute(level):
            self._state = State.DISTRIBUTE_STATS
        else:
            self._state = State.WAIT

    def _do_navigate_to_spot(self) -> None:
        if self._navigator is None:
            self._state = State.WAIT
            return

        try:
            success = self._navigator.navigate_to_spot(self._wm)
        except GameWindowError:
            self._state = State.CHECK_GAME_ALIVE
            return

        if success:
            self._needs_navigation = False
            self._state = State.WAIT
        else:
            logger.error("Navigation to spot failed — entering error pause")
            self._state = State.ERROR_PAUSE
            self._error_pause_seconds = 60

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

    def _do_wait(self) -> None:
        logger.debug("Waiting %ds before next cycle", self._config.loop_interval_seconds)
        time.sleep(self._config.loop_interval_seconds)
        self._state = State.CHECK_GAME_ALIVE

    def _do_error_pause(self) -> None:
        logger.info("Error pause: sleeping %ds before retry", self._error_pause_seconds)
        time.sleep(self._error_pause_seconds)
        self._state = State.CHECK_GAME_ALIVE
