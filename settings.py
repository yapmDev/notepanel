import json
from pathlib import Path

SETTINGS_DIR = Path.home() / ".config" / "notepanel"
SETTINGS_PATH = SETTINGS_DIR / "settings.json"

CORNERS = ("top-right", "top-left", "bottom-right", "bottom-left")

DEFAULTS = {
    "corner": "top-right",
    "width_percent": 20,
    "height_percent": 100,
}


def load_settings() -> dict:
    settings = DEFAULTS.copy()
    if SETTINGS_PATH.exists():
        try:
            data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                settings.update({k: v for k, v in data.items() if k in DEFAULTS})
        except (json.JSONDecodeError, OSError):
            pass

    if settings["corner"] not in CORNERS:
        settings["corner"] = DEFAULTS["corner"]
    settings["width_percent"] = min(100, max(1, int(settings["width_percent"])))
    settings["height_percent"] = min(100, max(1, int(settings["height_percent"])))
    return settings


def save_settings(settings: dict):
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    data = {
        "corner": settings.get("corner", DEFAULTS["corner"]),
        "width_percent": settings.get("width_percent", DEFAULTS["width_percent"]),
        "height_percent": settings.get("height_percent", DEFAULTS["height_percent"]),
    }
    SETTINGS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
