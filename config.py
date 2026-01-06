import os
from pathlib import Path

# Directories
PROJECT_ROOT = Path(__file__).resolve().parent
_DESKTOP = Path(os.environ.get("USERPROFILE", Path.home())) / "Desktop"
LOG_DIR = _DESKTOP / "limbus_automation_logs"
ASSETS_DIR = PROJECT_ROOT / "assets"

# Window / process configuration
GAME_WINDOW_TITLE = "LimbusCompany"
GAME_PROCESS_NAMES = ["LimbusCompany.exe", "Limbus Company.exe"]
MONITOR_INDEX = 1  # 1-based index used by mss
STEAM_GAME_URI = "steam://rungameid/1973530"
STEAM_APP_LAUNCH = ["steam.exe", "-applaunch", "1973530"]

# Timeouts (seconds)
STATE_TIMEOUTS = {
    "S1_WAIT_LOGIN": 30.0,
    "S2_CLICK_LOGIN": 5.0,
    "S3_WAIT_MAINMENU": 45.0,
    "GAME_BOOT": 60.0,
}

# Game readiness
GAME_READY_TIMEOUT = 180.0
GAME_READY_CHECK_INTERVAL = 0.5

# Polling intervals
CHECK_INTERVAL = 0.5
CLICK_INTERVAL = 2.0
CLICK_COOLDOWN = 2.5

# Template match settings
TEMPLATE_MATCH_THRESHOLD = 0.85

# Assets
LOGIN_MARKER = ASSETS_DIR / "login_marker_A.png"
LOGIN_UI_MARKER = ASSETS_DIR / "login_ui_marker.png"
CONNECTING_MARKER = ASSETS_DIR / "connecting_marker.png"
MAINMENU_MARKER = ASSETS_DIR / "mainmenu_marker_B.png"
