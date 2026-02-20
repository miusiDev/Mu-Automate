"""Constants for MU Supervisor."""

# Default HSV range for MU Online golden text
DEFAULT_HSV_LOWER = (15, 80, 150)
DEFAULT_HSV_UPPER = (45, 255, 255)

# OCR character corrections (common misreads)
OCR_CHAR_FIXES = {
    "O": "0",
    "o": "0",
    "Q": "0",
    "D": "0",
    "I": "1",
    "l": "1",
    "|": "1",
    "i": "1",
    "S": "5",
    "s": "5",
    "B": "8",
    "b": "6",
    "G": "6",
    "g": "9",
    "Z": "2",
    "z": "2",
    "T": "7",
    "A": "4",
}

# Tesseract PSM modes
PSM_SINGLE_LINE = 7
PSM_SINGLE_WORD = 8

# Stat commands used in MU Online chat
STAT_COMMANDS = {
    "str": "/addstr",
    "agi": "/addagi",
    "vit": "/addvit",
    "ene": "/addene",
}

# Max points per single /add command
MAX_POINTS_PER_COMMAND = 65000

# OCR consecutive failure threshold
OCR_FAILURE_THRESHOLD = 5
OCR_FAILURE_PAUSE_SECONDS = 300  # 5 minutes

# Web retry limits
CAPTCHA_MAX_RETRIES = 3
WEB_RESET_PAUSE_SECONDS = 600  # 10 minutes

# Game launch retry
LAUNCH_FAILURE_PAUSE_SECONDS = 600  # 10 minutes

# Timing delays for keyboard/command interaction
CHAT_OPEN_DELAY = 1.0
COMMAND_SEND_DELAY = 1.0
TYPE_CHAR_DELAY = 0.05

# Timeouts for launcher and game window detection (seconds)
LAUNCHER_WINDOW_TIMEOUT = 30
GAME_WINDOW_TIMEOUT = 60
CHAR_SELECT_TIMEOUT = 30

# Navigation constants
NAVIGATION_CLICK_RADIUS = 200  # pixels from window center for movement clicks
NAVIGATION_COORD_PATTERN = r"(\d{1,3})\s*,\s*(\d{1,3})"  # matches "X , Y" — requires comma separator

# Warp menu timing
WARP_MENU_DELAY = 1.0  # delay after pressing M to open warp menu
WARP_TRAVEL_DELAY = 3.0  # delay after clicking warp destination

# Reset timing
RESET_DISCONNECT_DELAY = 8  # seconds to wait after /reset before reconnecting
POST_RECONNECT_DELAY = 10  # seconds to wait after clicking Connect

# MU Helper stagnation detection
HELPER_RETRY_TIMEOUT = 10   # seconds before re-enabling MU Helper
HELPER_STUCK_TIMEOUT = 90   # seconds before giving up and re-navigating (must be > RETRY)
FARM_CHECK_INTERVAL = 5     # polling interval during middle_click farming
