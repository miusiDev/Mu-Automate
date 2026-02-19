"""Diagnostic: click in 4 screen directions and see how game coords change."""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pyautogui
import win32gui
from mu_supervisor.config import Config
from mu_supervisor.window_manager import WindowManager
from mu_supervisor.ocr_reader import OcrReader

CLICK_RADIUS = 200


def read_pos(ocr, wm, retries=3):
    """Read coordinates with retries."""
    for _ in range(retries):
        coords = ocr.read_coordinates(wm)
        if coords:
            return coords
        time.sleep(0.5)
    return None


def click_direction(wm, dx, dy):
    """Click at offset from window center and hold 200ms."""
    hwnd = wm.hwnd
    rect = win32gui.GetWindowRect(hwnd)
    cx = (rect[0] + rect[2]) // 2
    cy = (rect[1] + rect[3]) // 2

    wm.focus_window()
    pyautogui.moveTo(cx + dx, cy + dy)
    pyautogui.mouseDown()
    time.sleep(0.2)
    pyautogui.mouseUp()


def test_direction(name, wm, ocr, screen_dx, screen_dy):
    """Click in a direction and report coordinate change."""
    before = read_pos(ocr, wm)
    if not before:
        print(f"  {name}: No pude leer coords ANTES del click")
        return

    click_direction(wm, screen_dx, screen_dy)
    time.sleep(2.0)  # wait for character to walk

    after = read_pos(ocr, wm)
    if not after:
        print(f"  {name}: pos=({before[0]},{before[1]}) -> No pude leer coords DESPUES")
        return

    dx = after[0] - before[0]
    dy = after[1] - before[1]
    print(f"  {name}: ({before[0]},{before[1]}) -> ({after[0]},{after[1]})  delta=({dx:+d}, {dy:+d})")


def main():
    config = Config.from_yaml("config.yaml")
    wm = WindowManager(config.window_title)
    ocr = OcrReader(config)

    print("Buscando ventana...")
    wm.find_window()

    pos = read_pos(ocr, wm)
    if pos:
        print(f"Posición inicial: ({pos[0]}, {pos[1]})")
    else:
        print("No pude leer posición inicial!")

    directions = [
        ("SCREEN RIGHT  (+x, 0)", CLICK_RADIUS, 0),
        ("SCREEN DOWN   (0, +y)", 0, CLICK_RADIUS),
        ("SCREEN LEFT   (-x, 0)", -CLICK_RADIUS, 0),
        ("SCREEN UP     (0, -y)", 0, -CLICK_RADIUS),
    ]

    print("\nTesteando 4 direcciones de pantalla:\n")
    for name, sdx, sdy in directions:
        test_direction(name, wm, ocr, sdx, sdy)
        time.sleep(1.0)

    print("\nListo! Con estos deltas podemos corregir la fórmula isométrica.")


if __name__ == "__main__":
    main()
