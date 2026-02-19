# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MU Online automation supervisor for a private server (HeroesMu). Runs as a long-lived process on Windows that automates the full reset cycle: launch game, navigate through farming spots (Lorencia → Devias4 → LostTower6), distribute stats, and `/reset` at level 400 to repeat.

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
READ_STATUS → NAVIGATE_AND_FARM (active farming spot for current level)
            → RESET (level >= 400)
            → DISTRIBUTE_STATS (enough levels accumulated)
            → WAIT
NAVIGATE_AND_FARM → warp (if spot has warp_button) → walk (if spot has coords)
                  → farm (hold_right_click or middle_click) → READ_STATUS
RESET → /reset chat command → wait 6s → click Connect → CHECK_GAME_ALIVE
WAIT → CHECK_GAME_ALIVE (loop)
Any error → ERROR_PAUSE → CHECK_GAME_ALIVE
```

### Farming cycle (config.yaml `navigation.spots`)

Each spot defines a level range, action, and optional warp/navigation:

| Spot | Until Level | Action | Notes |
|------|------------|--------|-------|
| Lorencia | 50 | `hold_right_click` | Walk via waypoints, hold right-click to attack |
| Devias4 | 150 | `middle_click` | Warp via M menu, walk to spot, activate MU Helper |
| LostTower6 | 400 | `middle_click` | Warp via M menu, spawn = spot, activate MU Helper |

`_get_active_spot(level)` picks the first spot where `level < until_level`. After level 400, RESET sends `/reset` and clicks Connect to restart the cycle at level 1.

### Key modules (all in `mu_supervisor/`)

- **supervisor.py** — State machine (`State` enum + `Supervisor` class). Orchestrates all other modules.
- **window_manager.py** — Find/focus game window by title, capture screen regions (BitBlt with pyautogui fallback for DirectX windows). Returns BGR numpy arrays.
- **ocr_reader.py** — HSV golden-text filter + Tesseract OCR. Reads level (from window title first, OCR fallback), experience, and map coordinates. Has character-fix table (`OCR_CHAR_FIXES`) for common misreads.
- **navigator.py** — Isometric click-walk navigation and map warping. `warp_to()` opens M menu and clicks destination. `navigate_to()` walks through waypoints to a spot. Isometric formula: `screen_dx = game_dx + game_dy; screen_dy = game_dx - game_dy`. Detects stuck-against-wall and detours perpendicular.
- **game_launcher.py** — Full login sequence: launch exe (elevated via `ShellExecuteW runas`), click through launcher UI (server select, password paste, connect). All coordinates come from `config.yaml`.
- **stat_distributor.py** — Distributes stat points every N levels by pasting `/addstr`, `/addagi`, etc. commands into game chat. Chunks to 65000 max per command. Exports `send_chat_command()` used by supervisor for `/reset`.
- **config.py** — YAML → dataclass hierarchy (`Config`, `LauncherConfig`, `NavigationConfig`, `FarmingSpot`, `StatsConfig`, `OcrRegions`, `Region`, `Point`).
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
