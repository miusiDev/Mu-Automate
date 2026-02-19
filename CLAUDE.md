# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MU Online automation supervisor for a private server (HeroesMu). Runs as a long-lived process on Windows that monitors the game via OCR/window capture, auto-relaunches on crash, navigates the character to a farming spot, and distributes stat points via in-game chat commands.

**Windows-only** — depends on Win32 APIs (`win32gui`, `win32ui`, `win32con`, `ctypes.windll`), `pyautogui`, `pydirectinput`, and Tesseract OCR.

## Running

```bash
python run.py                  # uses config.yaml by default
python run.py my_config.yaml   # custom config path
```

## Calibration/Debug Tools

```bash
python tools/calibrate_coords.py   # capture coords region, show OCR result
python tools/test_navigation.py    # test walk-to-spot from current position
python tools/test_directions.py    # click 4 screen directions, report coord deltas
```

These require the game to be running and visible on screen.

## Architecture

The system is a **state machine** driven by `Supervisor._tick()`:

```
CHECK_GAME_ALIVE → LAUNCH_GAME (if dead) → CHECK_GAME_ALIVE
                 → READ_STATUS (if alive)
READ_STATUS → NAVIGATE_TO_SPOT (level < 30, after relaunch)
            → DISTRIBUTE_STATS (enough levels accumulated)
            → WAIT
WAIT → CHECK_GAME_ALIVE (loop)
Any error → ERROR_PAUSE → CHECK_GAME_ALIVE
```

### Key modules (all in `mu_supervisor/`)

- **supervisor.py** — State machine (`State` enum + `Supervisor` class). Orchestrates all other modules.
- **window_manager.py** — Find/focus game window by title, capture screen regions (BitBlt with pyautogui fallback for DirectX windows). Returns BGR numpy arrays.
- **ocr_reader.py** — HSV golden-text filter + Tesseract OCR. Reads level (from window title first, OCR fallback), experience, and map coordinates. Has character-fix table (`OCR_CHAR_FIXES`) for common misreads.
- **navigator.py** — Isometric click-walk navigation. Converts game coordinate deltas to screen clicks using `screen_dx = game_dx + game_dy; screen_dy = game_dx - game_dy`. Follows waypoints, detects stuck-against-wall, detours perpendicular.
- **game_launcher.py** — Full login sequence: launch exe (elevated via `ShellExecuteW runas`), click through launcher UI (server select, password paste, connect). All coordinates come from `config.yaml`.
- **stat_distributor.py** — Distributes stat points every N levels by pasting `/addstr`, `/addagi`, etc. commands into game chat. Chunks to 65000 max per command.
- **config.py** — YAML → dataclass hierarchy (`Config`, `LauncherConfig`, `NavigationConfig`, `StatsConfig`, `OcrRegions`, `Region`, `Point`).
- **constants.py** — HSV ranges, OCR fixes, timing delays, timeout values, stat command strings.
- **exceptions.py** — Custom hierarchy rooted at `MuSupervisorError`.

### Configuration

All screen coordinates, OCR regions, waypoints, stat ratios, and timing values live in `config.yaml`. Launcher button positions and the password are also there — these are pixel coordinates tied to a specific screen resolution.

### Input interaction pattern

The codebase uses **clipboard paste** (`pyperclip.copy()` + `pydirectinput` Ctrl+V) instead of typing, because `pydirectinput` has issues with `/` on non-US keyboard layouts. Mouse clicks use `pyautogui.moveTo()` + manual `mouseDown()`/`mouseUp()` with 200ms hold.

## Dependencies

Python 3.13+. Key packages: `pyautogui`, `pydirectinput`, `pyperclip`, `pytesseract`, `opencv-python` (`cv2`), `numpy`, `pywin32` (`win32gui`/`win32ui`/`win32con`), `PyYAML`, `colorlog`. Requires Tesseract OCR installed separately (path configured in `config.yaml`).

## Language

Code is in English. Comments and tool output strings are in Spanish.
