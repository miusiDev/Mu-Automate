"""Game crash detection, launch, and full login sequence."""

from __future__ import annotations

import ctypes
import logging
import os
import time
from typing import Optional

import pyautogui
import pyperclip
import pydirectinput

from .config import Config
from .constants import (
    GAME_WINDOW_TIMEOUT,
    LAUNCHER_WINDOW_TIMEOUT,
)
from .exceptions import LaunchError
from .window_manager import WindowManager

logger = logging.getLogger("mu_supervisor")


class GameLauncher:
    """Detect game crashes and relaunch through a configurable launcher.

    The login sequence is defined by ``config.launcher.login_steps`` — a list
    of click/paste actions with coordinates and timing.
    """

    def __init__(self, config: Config, wm: WindowManager) -> None:
        self._config = config
        self._wm = wm

    # ------------------------------------------------------------------
    # Status check
    # ------------------------------------------------------------------

    def is_game_running(self) -> bool:
        """Check if the game window is still alive."""
        if self._wm.is_window_alive():
            return True

        # Window handle is stale — try to rediscover
        try:
            self._wm.find_window()
            return True
        except Exception as exc:
            logger.warning("Game window not found: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Launch + login sequence
    # ------------------------------------------------------------------

    def launch_and_login(self) -> None:
        """Execute the full launch → login → connect sequence."""
        lc = self._config.launcher
        exe = lc.exe_path
        logger.info("Launching game from %s", exe)

        # Open the launcher (with elevation — the game requires admin)
        try:
            cwd = os.path.dirname(os.path.abspath(exe))
            result = ctypes.windll.shell32.ShellExecuteW(
                None, "runas", os.path.abspath(exe), None, cwd, 1,
            )
            if result <= 32:
                raise OSError(f"ShellExecuteW returned error code {result}")
        except OSError as exc:
            raise LaunchError(f"Failed to start launcher: {exc}") from exc

        # Wait for launcher window
        launcher_hwnd = self._wait_for_window(
            lc.launcher_window_title, LAUNCHER_WINDOW_TIMEOUT,
        )
        if launcher_hwnd is None:
            raise LaunchError("Launcher window did not appear in time")
        time.sleep(5)  # let the UI settle

        # Execute each login step
        for i, step in enumerate(lc.login_steps, 1):
            pt = step.point

            if step.action == "paste":
                logger.info(
                    "Step %d/%d [%s]: paste at (%d, %d)",
                    i, len(lc.login_steps), step.label, pt.x, pt.y,
                )
                pyautogui.moveTo(pt.x, pt.y)
                pyautogui.mouseDown()
                time.sleep(0.2)
                pyautogui.mouseUp()
                time.sleep(1)
                pyperclip.copy(step.text or "")
                pydirectinput.keyDown("ctrl")
                pydirectinput.press("v")
                pydirectinput.keyUp("ctrl")
            else:  # click
                logger.info(
                    "Step %d/%d [%s]: click at (%d, %d)",
                    i, len(lc.login_steps), step.label, pt.x, pt.y,
                )
                pyautogui.moveTo(pt.x, pt.y)
                time.sleep(1)
                pyautogui.mouseDown()
                time.sleep(0.2)
                pyautogui.mouseUp()

            if step.wait_after > 0:
                time.sleep(step.wait_after)

        # Wait for the game window to appear
        game_hwnd = self._wait_for_window(
            self._config.window_title, GAME_WINDOW_TIMEOUT, exact=False
        )
        if game_hwnd is None:
            raise LaunchError("Game window did not appear after login sequence")

        # Store the handle so the supervisor recognises the window on next tick
        self._wm._hwnd = game_hwnd
        time.sleep(2)  # let the title update with level info
        logger.info("Game window appeared (HWND=%s) — login complete", game_hwnd)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _wait_for_window(title: str, timeout: float, exact: bool = False) -> Optional[int]:
        """Poll for a window matching *title* to appear within *timeout* seconds."""
        import win32gui

        deadline = time.time() + timeout
        while time.time() < deadline:
            results: list[int] = []

            def _enum_cb(hwnd: int, _: None) -> None:
                if win32gui.IsWindowVisible(hwnd):
                    wt = win32gui.GetWindowText(hwnd)
                    if exact:
                        match = wt.lower() == title.lower()
                    else:
                        match = title.lower() in wt.lower()
                    if match:
                        results.append(hwnd)

            win32gui.EnumWindows(_enum_cb, None)

            if results:
                return results[0]

            time.sleep(1)

        return None
