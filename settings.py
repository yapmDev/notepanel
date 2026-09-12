import json
from pathlib import Path

SETTINGS_DIR = Path.home() / ".config" / "notepanel"
SETTINGS_PATH = SETTINGS_DIR / "settings.json"

CORNERS = ("top-right", "top-left", "bottom-right", "bottom-left", "center")

# The two shapes the notes list can take — the trash, being the same list
# with different rows in it, follows the same setting.
NOTES_VIEWS = ("list", "grid")

# App-defined geometry default: fixed, not user-configurable. Used as the
# initial corner/size and as the target of "reset position and size".
DEFAULT_CORNER = "center"
DEFAULT_WIDTH_PERCENT = 25
DEFAULT_HEIGHT_PERCENT = 50

# Minutes the last open note stays "current": reopening the panel within this
# window jumps straight back into the editor, after it the notes list is shown.
# 0 disables the shortcut entirely.
DEFAULT_REMEMBER_NOTE_MINUTES = 3
MAX_REMEMBER_NOTE_MINUTES = 1440

DEFAULTS = {
    "corner": DEFAULT_CORNER,
    "width_percent": DEFAULT_WIDTH_PERCENT,
    "height_percent": DEFAULT_HEIGHT_PERCENT,
    "hide_on_focus_out": False,
    "remember_note_minutes": DEFAULT_REMEMBER_NOTE_MINUTES,
    "notes_view": "list",
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
    if settings["notes_view"] not in NOTES_VIEWS:
        settings["notes_view"] = DEFAULTS["notes_view"]
    try:
        minutes = int(settings["remember_note_minutes"])
    except (TypeError, ValueError):
        minutes = DEFAULTS["remember_note_minutes"]
    settings["remember_note_minutes"] = min(MAX_REMEMBER_NOTE_MINUTES, max(0, minutes))
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


def save_notes_view(view: str):
    settings = load_settings()
    settings["notes_view"] = view
    save_settings(settings)


def clear_remembered_geometry() -> dict:
    settings = load_settings()
    settings["last_x"] = None
    settings["last_y"] = None
    settings["last_width"] = None
    settings["last_height"] = None
    save_settings(settings)
    return settings


def reset_geometry() -> dict:
    settings = load_settings()
    settings["corner"] = DEFAULT_CORNER
    settings["width_percent"] = DEFAULT_WIDTH_PERCENT
    settings["height_percent"] = DEFAULT_HEIGHT_PERCENT
    save_settings(settings)
    return clear_remembered_geometry()
