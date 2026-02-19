"""Test navigation: walk to the farming spot from current position."""

import sys
import os
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import cv2
from mu_supervisor.config import Config
from mu_supervisor.window_manager import WindowManager
from mu_supervisor.ocr_reader import OcrReader
from mu_supervisor.navigator import Navigator

logging.basicConfig(level=logging.DEBUG, format="%(levelname)s: %(message)s")


def main() -> None:
    config = Config.from_yaml("config.yaml")
    wm = WindowManager(config.window_title)
    ocr = OcrReader(config)
    nav = Navigator(config, ocr)

    print("Buscando ventana del juego...")
    wm.find_window()

    # Debug: save a capture first
    region = config.navigation.coords_region
    try:
        raw_img = wm.capture_region(region)
        cv2.imwrite("tools/nav_debug.png", raw_img)
        print(f"Captura guardada en tools/nav_debug.png ({raw_img.shape})")
    except Exception as e:
        print(f"Error capturando: {e}")

    coords = ocr.read_coordinates(wm)
    if coords:
        print(f"Posición actual: ({coords[0]}, {coords[1]})")
    else:
        print("No pude leer coordenadas iniciales, pero intento navegar igual...")

    spot = config.navigation.spot
    print(f"Destino: ({spot.x}, {spot.y})")
    print("Navegando...\n")

    success = nav.navigate_to_spot(wm)

    if success:
        print("\nLlegó al spot!")
    else:
        print("\nNo pudo llegar al spot.")


if __name__ == "__main__":
    main()
