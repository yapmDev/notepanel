import gi
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk

import settings as settings_mod


def get_target_geometry() -> tuple[int, int, int, int]:
    prefs = settings_mod.load_settings()
    corner = prefs["corner"]
    width_ratio = prefs["width_percent"] / 100
    height_ratio = prefs["height_percent"] / 100

    display = Gdk.Display.get_default()
    monitor = display.get_primary_monitor() or display.get_monitor(0)
    geo = monitor.get_geometry()
    work = monitor.get_workarea()
    has_work = work.height > 0

    w = int(geo.width * width_ratio)
    h = int((work.height if has_work else geo.height) * height_ratio)

    x = geo.x if "left" in corner else geo.x + geo.width - w

    top = work.y if has_work else geo.y
    bottom_area_end = (work.y + work.height) if has_work else (geo.y + geo.height)
    y = top if "top" in corner else bottom_area_end - h

    return x, y, w, h


def apply_geometry(window, x: int, y: int, w: int, h: int):
    window.set_size_request(w, h)
    gdk_win = window.get_window()
    if gdk_win:
        gdk_win.move_resize(x, y, w, h)
    else:
        window.resize(w, h)
        window.move(x, y)
