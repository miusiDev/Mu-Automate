"""Calibration tool: capture the coords region and show what OCR reads."""

import atexit
import ctypes
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import cv2
from mu_supervisor.config import Config
from mu_supervisor.window_manager import WindowManager
from mu_supervisor.ocr_reader import OcrReader


def _release_modifier_keys() -> None:
    """Release ALT, CTRL, SHIFT in case they got stuck."""
    keybd_event = ctypes.windll.user32.keybd_event
    KEYEVENTF_KEYUP = 0x0002
    for vk in (0x12, 0x10, 0x11):  # ALT, SHIFT, CTRL
        keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)


atexit.register(_release_modifier_keys)


def main() -> None:
    config_path = sys.argv[1] if len(sys.argv) > 1 else "config.yaml"
    config = Config.from_yaml(config_path)
    wm = WindowManager(config.window_title)
    ocr = OcrReader(config)

    print("Buscando ventana del juego...")
    wm.find_window()

    region = config.navigation.coords_region
    print(f"Capturando región: x={region.x}, y={region.y}, w={region.w}, h={region.h}")

    raw_img = wm.capture_region(region)

    # Guardar imagen original y filtrada
    cv2.imwrite("tools/coords_raw.png", raw_img)

    filtered = ocr.filter_golden_text(raw_img)
    cv2.imwrite("tools/coords_filtered.png", filtered)

    # Mostrar ampliado
    scale = 6
    h, w = raw_img.shape[:2]
    big = cv2.resize(raw_img, (w * scale, h * scale), interpolation=cv2.INTER_NEAREST)
    cv2.imshow("Coords Region (raw) - Presiona cualquier tecla para cerrar", big)

    big_f = cv2.resize(filtered, (w * scale, h * scale), interpolation=cv2.INTER_NEAREST)
    cv2.imshow("Coords Region (filtered) - Presiona cualquier tecla para cerrar", big_f)

    # Intentar OCR
    coords = ocr.read_coordinates(wm)
    if coords:
        print(f"\nOCR leyó coordenadas: X={coords[0]}, Y={coords[1]}")
    else:
        print("\nOCR no pudo leer coordenadas. Ajustá coords_region en config.yaml")

    print("\nPresioná cualquier tecla en la ventana de imagen para cerrar.")
    cv2.waitKey(0)
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
