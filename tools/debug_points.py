"""Debug tool: open character screen (C), capture points_region, show OCR result."""

import atexit
import ctypes
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import re
import time
import cv2
import pydirectinput
import pytesseract
from mu_supervisor.config import Config
from mu_supervisor.window_manager import WindowManager


def _release_modifier_keys() -> None:
    keybd_event = ctypes.windll.user32.keybd_event
    for vk in (0x12, 0x10, 0x11):
        keybd_event(vk, 0, 0x0002, 0)


atexit.register(_release_modifier_keys)


def main() -> None:
    config_path = sys.argv[1] if len(sys.argv) > 1 else "config.yaml"
    config = Config.from_yaml(config_path)
    pytesseract.pytesseract.tesseract_cmd = config.tesseract_path

    wm = WindowManager(config.window_title)
    print("Buscando ventana del juego...")
    wm.find_window()

    region = config.stats.points_region
    if region is None:
        print("No hay points_region configurado en stats.")
        return

    print(f"points_region: x={region.x}, y={region.y}, w={region.w}, h={region.h}")

    # Abrir pantalla de personaje
    wm.focus_window()
    print("Abriendo pantalla de personaje (C)...")
    pydirectinput.press("c")
    time.sleep(0.5)

    raw_img = wm.capture_region(region)

    # Cerrar pantalla de personaje
    pydirectinput.press("c")

    cv2.imwrite("tools/points_raw.png", raw_img)

    # Escalar y threshold
    h, w = raw_img.shape[:2]
    scaled = cv2.resize(raw_img, (w * 3, h * 3), interpolation=cv2.INTER_CUBIC)
    gray = cv2.cvtColor(scaled, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 128, 255, cv2.THRESH_BINARY)

    cv2.imwrite("tools/points_thresh.png", thresh)

    # OCR
    text = pytesseract.image_to_string(
        thresh,
        config="--psm 7 -c tessedit_char_whitelist=0123456789",
    ).strip()

    digits = re.sub(r"\D", "", text)
    points = int(digits) if digits else 0

    print(f"\nImagen guardada en: tools/points_raw.png")
    print(f"Threshold guardado en: tools/points_thresh.png")
    print(f"OCR texto raw: '{text}'")
    print(f"Puntos leidos: {points}")

    # Mostrar ampliado
    scale = 6
    big = cv2.resize(raw_img, (w * scale, h * scale), interpolation=cv2.INTER_NEAREST)
    cv2.imshow("Points Region (raw)", big)
    big_t = cv2.resize(thresh, (w * 3 * scale, h * 3 * scale), interpolation=cv2.INTER_NEAREST)
    cv2.imshow("Points Region (threshold)", big_t)

    print("\nPresiona cualquier tecla en la ventana de imagen para cerrar.")
    cv2.waitKey(0)
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
