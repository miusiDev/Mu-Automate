"""Interactive calibration tool for recording a launcher login sequence.

Records mouse clicks in real-time using global hotkeys and generates
a YAML config with the login_steps list.

Hotkeys (work globally):
    F2 = Capture CLICK step at current mouse position
    F3 = Capture PASTE step (prompts for text to paste)
    F4 = Finish recording

Requires: pyautogui (already a project dependency).
Uses ctypes for global hotkey detection — no extra packages needed.
"""

from __future__ import annotations

import ctypes
import getpass
import os
import sys
import time
from typing import Any, Dict, List

import pyautogui
import yaml

# Virtual key codes
VK_F2 = 0x71
VK_F3 = 0x72
VK_F4 = 0x73

GetAsyncKeyState = ctypes.windll.user32.GetAsyncKeyState

# Defaults for new server configs (non-launcher fields)
DEFAULT_CONFIG_TEMPLATE: Dict[str, Any] = {
    "window_title": "HeroesMu",
    "tesseract_path": "E:/Tesseract-OCR/tesseract.exe",
    "ocr_regions": {
        "level": {"x": 580, "y": 460, "w": 80, "h": 20},
        "experience": {"x": 580, "y": 480, "w": 120, "h": 20},
    },
    "stats": {
        "interval_levels": 50,
        "points_per_level": 5,
        "distribution": {"str": 0.1, "agi": 0.3, "vit": 0.1, "ene": 0.5},
    },
    "reset_level": 400,
    "navigation": {
        "coords_region": {"x": 155, "y": 30, "w": 95, "h": 25},
        "tolerance": 1,
        "step_delay": 1.5,
        "max_steps": 100,
        "spots": [],
    },
    "loop_interval_seconds": 30,
    "log_level": "INFO",
}


def key_just_pressed(vk: int) -> bool:
    """Return True if the key was pressed since the last call."""
    # Bit 0 = pressed since last query, bit 15 = currently down
    state = GetAsyncKeyState(vk)
    return bool(state & 0x0001)


def wait_for_key(vk: int) -> None:
    """Block until the given key is pressed."""
    # Drain any stale press
    GetAsyncKeyState(vk)
    while True:
        if key_just_pressed(vk):
            return
        time.sleep(0.05)


def record_steps() -> List[Dict[str, Any]]:
    """Record login steps interactively, returning raw step dicts."""
    steps: List[Dict[str, Any]] = []
    timestamps: List[float] = []

    print("\n[Grabando] Presiona F2 en cada boton, F3 para campos de texto, F4 para terminar...\n")

    # Drain any pending key states
    for vk in (VK_F2, VK_F3, VK_F4):
        GetAsyncKeyState(vk)

    while True:
        time.sleep(0.05)

        if key_just_pressed(VK_F4):
            print("  [F4] Listo!\n")
            break

        if key_just_pressed(VK_F2):
            x, y = pyautogui.position()
            now = time.time()
            label = input(f"  Step {len(steps) + 1}: CLICK en ({x}, {y})  —  Label: ").strip() or f"Step {len(steps) + 1}"
            steps.append({
                "action": "click",
                "label": label,
                "point": {"x": x, "y": y},
            })
            timestamps.append(now)

        if key_just_pressed(VK_F3):
            x, y = pyautogui.position()
            now = time.time()
            label = input(f"  Step {len(steps) + 1}: PASTE en ({x}, {y})  —  Label: ").strip() or f"Step {len(steps) + 1}"
            text = getpass.getpass("    Texto a pegar: ")
            steps.append({
                "action": "paste",
                "label": label,
                "point": {"x": x, "y": y},
                "text": text,
            })
            timestamps.append(now)

    # Compute wait_after from timestamps
    for i in range(len(steps)):
        if i < len(timestamps) - 1:
            wait = round(timestamps[i + 1] - timestamps[i])
            steps[i]["wait_after"] = max(wait, 0)
        else:
            steps[i]["wait_after"] = 0

    return steps


def record_reconnect_button() -> Dict[str, int]:
    """Ask the user to point at the reconnect button."""
    print("Ahora mueve el mouse al boton de RECONECTAR (usado despues de /reset) y presiona F2...")
    wait_for_key(VK_F2)
    x, y = pyautogui.position()
    print(f"  Boton de reconexion: ({x}, {y})\n")
    return {"x": x, "y": y}


def build_launcher_config(
    steps: List[Dict[str, Any]],
    connect_button: Dict[str, int],
) -> Dict[str, Any]:
    """Prompt for top-level fields and assemble the launcher config dict."""
    exe_path = input("Ruta del exe []: ").strip()
    window_title = input("Titulo de la ventana del launcher []: ").strip()

    return {
        "exe_path": exe_path,
        "launcher_window_title": window_title,
        "connect_button": connect_button,
        "login_steps": steps,
    }


def _prompt_with_default(prompt: str, default: Any) -> str:
    """Prompt the user with a default value shown in brackets."""
    raw = input(f"{prompt} [{default}]: ").strip()
    return raw if raw else str(default)


def build_full_config(launcher_cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Build a complete server config by prompting for all top-level fields.

    Uses DEFAULT_CONFIG_TEMPLATE for sensible defaults.
    """
    print("\n--- Configuracion general del servidor ---\n")

    tpl = DEFAULT_CONFIG_TEMPLATE
    window_title = _prompt_with_default(
        "Titulo de la ventana del juego", tpl["window_title"]
    )
    tesseract_path = _prompt_with_default(
        "Ruta de Tesseract OCR", tpl["tesseract_path"]
    )
    reset_level = int(_prompt_with_default("Nivel de reset", tpl["reset_level"]))

    config: Dict[str, Any] = {
        "window_title": window_title,
        "tesseract_path": tesseract_path,
        "ocr_regions": tpl["ocr_regions"],
        "stats": tpl["stats"],
        "reset_level": reset_level,
        "launcher": launcher_cfg,
        "navigation": tpl["navigation"],
        "loop_interval_seconds": tpl["loop_interval_seconds"],
        "log_level": tpl["log_level"],
    }
    return config


def save_config(launcher_cfg: Dict[str, Any]) -> None:
    """Save the launcher config and optionally merge into an existing config.yaml."""
    default_path = "config_launcher.yaml"
    out_path = input(f"Guardar en [{default_path}]: ").strip() or default_path

    with open(out_path, "w", encoding="utf-8") as fh:
        yaml.dump({"launcher": launcher_cfg}, fh, default_flow_style=False, sort_keys=False)
    print(f"\nGuardado en: {out_path}")

    merge = input("\nMergear en un config.yaml existente? [s/N]: ").strip().lower()
    if merge in ("s", "si", "y", "yes"):
        cfg_path = input("Ruta del config.yaml [config.yaml]: ").strip() or "config.yaml"
        if not os.path.isfile(cfg_path):
            print(f"  No se encontro {cfg_path}, omitiendo merge.")
            return
        with open(cfg_path, "r", encoding="utf-8") as fh:
            existing = yaml.safe_load(fh) or {}
        existing["launcher"] = launcher_cfg
        with open(cfg_path, "w", encoding="utf-8") as fh:
            yaml.dump(existing, fh, default_flow_style=False, sort_keys=False)
        print(f"  Mergeado en: {cfg_path}")


def calibrate_new_server(servers_dir: str) -> str:
    """Full calibration flow: record launcher + build complete config.

    Saves the config to servers_dir/{name}.yaml and returns the path.
    Called from server_manager menu or standalone.
    """
    print("\n=== Calibrar nuevo servidor ===\n")

    name = input("Nombre del servidor (ej: heroesmu): ").strip()
    if not name:
        print("Nombre vacio, cancelando.")
        sys.exit(1)

    print("\nHotkeys (funcionan con cualquier ventana activa):")
    print("  F2 = Capturar paso CLICK")
    print("  F3 = Capturar paso PASTE (pide texto)")
    print("  F4 = Terminar grabacion\n")
    print("1. Abre tu launcher y dejalo listo")
    print("2. Presiona F2/F3 en cada boton EN ORDEN")
    print("3. Espera naturalmente entre pasos (el timing se graba)\n")

    input("Presiona Enter para empezar a grabar...")

    steps = record_steps()

    if not steps:
        print("No se grabaron pasos. Saliendo.")
        sys.exit(1)

    print(f"Se grabaron {len(steps)} pasos.\n")
    for i, s in enumerate(steps, 1):
        action = s["action"].upper()
        pt = s["point"]
        wait = s["wait_after"]
        print(f"  {i}. [{action}] {s['label']} en ({pt['x']}, {pt['y']})  wait={wait}s")
    print()

    connect_button = record_reconnect_button()
    launcher_cfg = build_launcher_config(steps, connect_button)

    full_config = build_full_config(launcher_cfg)

    os.makedirs(servers_dir, exist_ok=True)
    out_path = os.path.join(servers_dir, f"{name}.yaml")
    with open(out_path, "w", encoding="utf-8") as fh:
        yaml.dump(full_config, fh, default_flow_style=False, sort_keys=False)
    print(f"\nConfig guardada en: {out_path}")

    return out_path


def main() -> None:
    print("=== Calibracion de Launcher MU ===\n")
    print("Hotkeys (funcionan con cualquier ventana activa):")
    print("  F2 = Capturar paso CLICK")
    print("  F3 = Capturar paso PASTE (pide texto)")
    print("  F4 = Terminar grabacion\n")
    print("1. Abre tu launcher y dejalo listo")
    print("2. Presiona F2/F3 en cada boton EN ORDEN")
    print("3. Espera naturalmente entre pasos (el timing se graba)\n")

    input("Presiona Enter para empezar a grabar...")

    steps = record_steps()

    if not steps:
        print("No se grabaron pasos. Saliendo.")
        sys.exit(1)

    print(f"Se grabaron {len(steps)} pasos.\n")
    for i, s in enumerate(steps, 1):
        action = s["action"].upper()
        pt = s["point"]
        wait = s["wait_after"]
        print(f"  {i}. [{action}] {s['label']} en ({pt['x']}, {pt['y']})  wait={wait}s")
    print()

    connect_button = record_reconnect_button()
    launcher_cfg = build_launcher_config(steps, connect_button)
    save_config(launcher_cfg)

    print("\nListo!")


if __name__ == "__main__":
    main()
