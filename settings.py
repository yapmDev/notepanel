import json
from pathlib import Path

SETTINGS_DIR = Path.home() / ".config" / "notepanel"
SETTINGS_PATH = SETTINGS_DIR / "settings.json"

CORNERS = ("top-right", "top-left", "bottom-right", "bottom-left")

DEFAULTS = {
    "corner": "top-right",
    "width_percent": 20,
    "height_percent": 100,
    "hide_on_focus_out": False,
    "remember_geometry": False,
    "last_x": None,
    "last_y": None,
    "last_width": None,
    "last_height": None,
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
    settings["hide_on_focus_out"] = bool(settings["hide_on_focus_out"])
    settings["remember_geometry"] = bool(settings["remember_geometry"])
    for key in ("last_x", "last_y", "last_width", "last_height"):
        value = settings[key]
        settings[key] = int(value) if isinstance(value, (int, float)) else None
    return settings


def save_settings(settings: dict):
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    data = {key: settings.get(key, DEFAULTS[key]) for key in DEFAULTS}
    SETTINGS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def save_geometry(x: int, y: int, w: int, h: int):
    settings = load_settings()
    settings["last_x"] = x
    settings["last_y"] = y
    settings["last_width"] = w
    settings["last_height"] = h
    save_settings(settings)


def clear_geometry():
    settings = load_settings()
    settings["last_x"] = None
    settings["last_y"] = None
    settings["last_width"] = None
    settings["last_height"] = None
    save_settings(settings)
