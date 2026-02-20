"""Prueba distintos métodos de middle click para activar MU Helper.

Uso: python tools/test_middle_click.py
Tener el juego abierto y el personaje en pantalla.
Cada método espera 3 segundos para que posiciones el mouse sobre el juego.
"""

import ctypes
import time

import pyautogui
import pydirectinput
import win32api
import win32con


def countdown(label: str, seconds: int = 3) -> None:
    print(f"\n{'='*50}")
    print(f"Siguiente: {label}")
    for i in range(seconds, 0, -1):
        print(f"  {i}...")
        time.sleep(1)
    print(f"  >> Ejecutando: {label}")


def method_1():
    """pyautogui.click(button='middle')"""
    countdown("pyautogui.click(button='middle')")
    pyautogui.click(button="middle")


def method_2():
    """pyautogui mouseDown/mouseUp 200ms"""
    countdown("pyautogui mouseDown/mouseUp 200ms")
    pyautogui.mouseDown(button="middle")
    time.sleep(0.2)
    pyautogui.mouseUp(button="middle")


def method_3():
    """pydirectinput.click(button='middle')"""
    countdown("pydirectinput.click(button='middle')")
    pydirectinput.click(button="middle")


def method_4():
    """pydirectinput mouseDown/mouseUp 200ms"""
    countdown("pydirectinput mouseDown/mouseUp 200ms")
    pydirectinput.mouseDown(button="middle")
    time.sleep(0.2)
    pydirectinput.mouseUp(button="middle")


def method_5():
    """win32api.mouse_event MIDDLEDOWN/MIDDLEUP 200ms"""
    countdown("win32api.mouse_event MIDDLE 200ms")
    win32api.mouse_event(win32con.MOUSEEVENTF_MIDDLEDOWN, 0, 0)
    time.sleep(0.2)
    win32api.mouse_event(win32con.MOUSEEVENTF_MIDDLEUP, 0, 0)


def method_6():
    """ctypes SendInput middle click"""
    countdown("ctypes SendInput middle click")

    MOUSEEVENTF_MIDDLEDOWN = 0x0020
    MOUSEEVENTF_MIDDLEUP = 0x0040

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [
            ("dx", ctypes.c_long),
            ("dy", ctypes.c_long),
            ("mouseData", ctypes.c_ulong),
            ("dwFlags", ctypes.c_ulong),
            ("time", ctypes.c_ulong),
            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
        ]

    class INPUT(ctypes.Structure):
        _fields_ = [
            ("type", ctypes.c_ulong),
            ("mi", MOUSEINPUT),
        ]

    extra = ctypes.c_ulong(0)

    down = INPUT()
    down.type = 0  # INPUT_MOUSE
    down.mi = MOUSEINPUT(0, 0, 0, MOUSEEVENTF_MIDDLEDOWN, 0, ctypes.pointer(extra))

    up = INPUT()
    up.type = 0
    up.mi = MOUSEINPUT(0, 0, 0, MOUSEEVENTF_MIDDLEUP, 0, ctypes.pointer(extra))

    ctypes.windll.user32.SendInput(1, ctypes.pointer(down), ctypes.sizeof(INPUT))
    time.sleep(0.2)
    ctypes.windll.user32.SendInput(1, ctypes.pointer(up), ctypes.sizeof(INPUT))


if __name__ == "__main__":
    print("Test de middle click para MU Helper")
    print("Posiciona el mouse sobre el juego y no lo muevas.")
    print("Cada método tiene 3 segundos de cuenta regresiva.")
    print("Observa cuál activa el MU Helper.\n")

    methods = [method_1, method_2, method_3, method_4, method_5, method_6]

    for i, method in enumerate(methods, 1):
        method()
        print(f"  >> Listo. ¿Funcionó? Observa el juego.")
        time.sleep(3)  # pausa para observar resultado

    print(f"\n{'='*50}")
    print("Test completo. ¿Alguno funcionó?")
