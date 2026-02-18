"""Window management: find, focus, and capture the MU Online game window."""

from __future__ import annotations

import ctypes
import logging
import time
from typing import Optional, Tuple

import numpy as np
import pyautogui
import win32con
import win32gui
import win32ui

from .config import Region
from .exceptions import GameWindowError

logger = logging.getLogger("mu_supervisor")


class WindowManager:
    """Locate, focus, and screenshot the MU Online window."""

    def __init__(self, window_title: str) -> None:
        self._title = window_title
        self._hwnd: Optional[int] = None

    @property
    def hwnd(self) -> Optional[int]:
        return self._hwnd

    # ------------------------------------------------------------------
    # Window discovery
    # ------------------------------------------------------------------

    def find_window(self) -> int:
        """Find the game window by title substring. Returns HWND."""
        results: list[int] = []

        def _enum_cb(hwnd: int, _: None) -> None:
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if title.lower() == self._title.lower():
                    results.append(hwnd)

        win32gui.EnumWindows(_enum_cb, None)

        if not results:
            self._hwnd = None
            raise GameWindowError(
                f"No visible window matching {self._title!r}"
            )

        self._hwnd = results[0]
        logger.debug("Found window HWND=%s title=%r", self._hwnd,
                      win32gui.GetWindowText(self._hwnd))
        return self._hwnd

    def is_window_alive(self) -> bool:
        """Check whether the stored HWND still refers to a live window."""
        if self._hwnd is None:
            return False
        if not win32gui.IsWindow(self._hwnd):
            self._hwnd = None
            return False
        if not win32gui.IsWindowVisible(self._hwnd):
            self._hwnd = None
            return False
        return True

    # ------------------------------------------------------------------
    # Focus
    # ------------------------------------------------------------------

    def focus_window(self) -> None:
        """Bring the game window to the foreground.

        Uses the ALT-key trick to bypass Windows' foreground restrictions.
        """
        if self._hwnd is None:
            raise GameWindowError("No window handle stored; call find_window() first")

        # Press ALT to allow SetForegroundWindow from background
        ctypes.windll.user32.keybd_event(0x12, 0, 0, 0)  # ALT down
        try:
            win32gui.ShowWindow(self._hwnd, win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(self._hwnd)
        finally:
            ctypes.windll.user32.keybd_event(0x12, 0, 2, 0)  # ALT up

        time.sleep(0.15)

    # ------------------------------------------------------------------
    # Screen capture
    # ------------------------------------------------------------------

    def capture_region(self, region: Region) -> np.ndarray:
        """Capture a region of the game window and return a BGR numpy array.

        Tries BitBlt first; falls back to pyautogui if the result is all black
        (common with DirectX exclusive-mode windows).
        """
        if self._hwnd is None:
            raise GameWindowError("No window handle stored; call find_window() first")

        img = self._capture_bitblt(region)
        if img is not None and img.any():
            return img

        logger.debug("BitBlt returned blank; falling back to pyautogui")
        return self._capture_pyautogui(region)

    # -- BitBlt path --

    def _capture_bitblt(self, region: Region) -> Optional[np.ndarray]:
        try:
            hwnd_dc = win32gui.GetWindowDC(self._hwnd)
            mfc_dc = win32ui.CreateDCFromHandle(hwnd_dc)
            save_dc = mfc_dc.CreateCompatibleDC()

            bmp = win32ui.CreateBitmap()
            bmp.CreateCompatibleBitmap(mfc_dc, region.w, region.h)
            save_dc.SelectObject(bmp)

            save_dc.BitBlt(
                (0, 0), (region.w, region.h),
                mfc_dc, (region.x, region.y),
                win32con.SRCCOPY,
            )

            bmp_info = bmp.GetInfo()
            bmp_bits = bmp.GetBitmapBits(True)

            img = np.frombuffer(bmp_bits, dtype=np.uint8)
            img = img.reshape(bmp_info["bmHeight"], bmp_info["bmWidth"], 4)
            img = img[:, :, :3]  # drop alpha → BGR

            # Cleanup
            save_dc.DeleteDC()
            mfc_dc.DeleteDC()
            win32gui.ReleaseDC(self._hwnd, hwnd_dc)
            bmp.DeleteObject()

            return img
        except Exception:
            logger.debug("BitBlt capture failed", exc_info=True)
            return None

    # -- pyautogui fallback path --

    def _capture_pyautogui(self, region: Region) -> np.ndarray:
        self.focus_window()

        rect = win32gui.GetWindowRect(self._hwnd)
        abs_x = rect[0] + region.x
        abs_y = rect[1] + region.y

        screenshot = pyautogui.screenshot(
            region=(abs_x, abs_y, region.w, region.h)
        )
        img = np.array(screenshot)
        # pyautogui returns RGB; convert to BGR for OpenCV
        return img[:, :, ::-1].copy()
