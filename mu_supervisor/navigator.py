"""Navigator: walk the character between farming spots and warp between maps."""

from __future__ import annotations

import logging
import math
import time

import pyautogui
import pydirectinput
import win32gui

from .config import Config, NavigationConfig, Point
from .constants import NAVIGATION_CLICK_RADIUS, WARP_MENU_DELAY, WARP_TRAVEL_DELAY
from .ocr_reader import OcrReader
from .window_manager import WindowManager

logger = logging.getLogger("mu_supervisor")

# How many consecutive steps with no movement before we consider "stuck"
STUCK_THRESHOLD = 3


class Navigator:
    """Read current coordinates via OCR and click-walk to farming spots.

    MU Online uses an isometric view where:
      - Game +X → screen down-right
      - Game +Y → screen down-left

    Screen offset from center:
      screen_dx = game_dx + game_dy
      screen_dy = game_dx - game_dy
    """

    def __init__(self, config: Config, ocr: OcrReader) -> None:
        nav = config.navigation
        if nav is None:
            raise ValueError("NavigationConfig is required for Navigator")
        self._nav: NavigationConfig = nav
        self._ocr = ocr

    # ------------------------------------------------------------------
    # Warp
    # ------------------------------------------------------------------

    @staticmethod
    def warp_to(wm: WindowManager, warp_button: Point) -> None:
        """Open the warp menu (M key) and click on a destination."""
        wm.focus_window()
        pydirectinput.press("m")
        time.sleep(WARP_MENU_DELAY)
        pyautogui.click(warp_button.x, warp_button.y)
        time.sleep(WARP_TRAVEL_DELAY)

    # ------------------------------------------------------------------
    # Walk navigation
    # ------------------------------------------------------------------

    def navigate_to(
        self, wm: WindowManager, spot: Point, waypoints: list[Point],
    ) -> bool:
        """Walk through waypoints then to the spot. Returns True if we arrived."""
        targets = [(wp.x, wp.y) for wp in waypoints] + [(spot.x, spot.y)]
        total_steps = 0

        for i, (target_x, target_y) in enumerate(targets):
            is_final = (i == len(targets) - 1)
            label = "spot" if is_final else f"waypoint {i + 1}"
            logger.info("Navigating to %s (%d, %d)", label, target_x, target_y)

            reached = self._walk_to(wm, target_x, target_y, total_steps)
            total_steps = reached[1]

            if not reached[0]:
                logger.warning("Failed to reach %s", label)
                return False

            logger.info("Reached %s!", label)

        return True

    def _walk_to(
        self, wm: WindowManager, target_x: int, target_y: int, step_offset: int
    ) -> tuple[bool, int]:
        """Walk to a single target. Returns (success, total_steps_used)."""
        tolerance = self._nav.tolerance
        prev_coords: tuple[int, int] | None = None
        stuck_count = 0
        detour_sign = 1

        for step in range(1, self._nav.max_steps + 1):
            global_step = step_offset + step

            coords = self._ocr.read_coordinates(wm)
            if coords is None:
                logger.warning("Step %d: could not read coordinates", global_step)
                time.sleep(self._nav.step_delay)
                continue

            cur_x, cur_y = coords
            dx = target_x - cur_x
            dy = target_y - cur_y
            distance = math.hypot(dx, dy)

            logger.info(
                "Step %d: pos=(%d,%d) target=(%d,%d) dist=%.1f",
                global_step, cur_x, cur_y, target_x, target_y, distance,
            )

            if distance <= tolerance:
                return (True, step_offset + step)

            # Detect stuck: coordinates didn't change since last step
            if prev_coords is not None and (cur_x, cur_y) == prev_coords:
                stuck_count += 1
                logger.info("Stuck count: %d/%d", stuck_count, STUCK_THRESHOLD)
            else:
                stuck_count = 0

            prev_coords = (cur_x, cur_y)

            if stuck_count >= STUCK_THRESHOLD:
                logger.info("Stuck against wall — detouring (sign=%d)", detour_sign)
                perp_dx = -dy * detour_sign
                perp_dy = dx * detour_sign
                self._click_towards(wm, perp_dx, perp_dy)
                stuck_count = 0
                detour_sign *= -1
            else:
                self._click_towards(wm, dx, dy)

            time.sleep(self._nav.step_delay)

        logger.warning("Gave up after %d steps", self._nav.max_steps)
        return (False, step_offset + self._nav.max_steps)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _click_towards(wm: WindowManager, game_dx: int, game_dy: int) -> None:
        """Click in the isometric screen direction corresponding to the game delta."""
        # Isometric conversion (calibrated from test_directions)
        screen_dx = game_dx + game_dy
        screen_dy = game_dx - game_dy

        # Normalize to a fixed click radius
        magnitude = math.hypot(screen_dx, screen_dy)
        if magnitude == 0:
            return

        norm_dx = screen_dx / magnitude * NAVIGATION_CLICK_RADIUS
        norm_dy = screen_dy / magnitude * NAVIGATION_CLICK_RADIUS

        # Find center of game window
        hwnd = wm.hwnd
        if hwnd is None:
            logger.warning("No window handle — cannot click")
            return

        rect = win32gui.GetWindowRect(hwnd)
        win_cx = (rect[0] + rect[2]) // 2
        win_cy = (rect[1] + rect[3]) // 2

        click_x = int(win_cx + norm_dx)
        click_y = int(win_cy + norm_dy)

        wm.focus_window()
        pyautogui.moveTo(click_x, click_y)
        pyautogui.mouseDown()
        time.sleep(0.2)
        pyautogui.mouseUp()
        logger.debug("Clicked (%d, %d) — game delta (%d, %d)", click_x, click_y, game_dx, game_dy)
