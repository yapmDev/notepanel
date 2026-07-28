import gi
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk

import settings as settings_mod


def get_target_geometry() -> tuple[int, int, int, int]:
    prefs = settings_mod.load_settings()

    display = Gdk.Display.get_default()
    monitor = display.get_primary_monitor() or display.get_monitor(0)
    geo = monitor.get_geometry()
    work = monitor.get_workarea()
    has_work = work.height > 0

    if None not in (
        prefs["last_x"], prefs["last_y"], prefs["last_width"], prefs["last_height"]
    ):
        w = prefs["last_width"]
        h = prefs["last_height"]
        area_x = work.x if has_work else geo.x
        area_y = work.y if has_work else geo.y
        area_w = work.width if has_work else geo.width
        area_h = work.height if has_work else geo.height
        x = min(max(prefs["last_x"], area_x), area_x + area_w - w)
        y = min(max(prefs["last_y"], area_y), area_y + area_h - h)
        return x, y, w, h

    corner = prefs["corner"]
    width_ratio = prefs["width_percent"] / 100
    height_ratio = prefs["height_percent"] / 100

    top = work.y if has_work else geo.y
    bottom_area_end = (work.y + work.height) if has_work else (geo.y + geo.height)

    w = int(geo.width * width_ratio)
    h = int((work.height if has_work else geo.height) * height_ratio)

    if corner == "center":
        x = geo.x + (geo.width - w) // 2
        y = top + (bottom_area_end - top - h) // 2
    else:
        x = geo.x if "left" in corner else geo.x + geo.width - w
        y = top if "top" in corner else bottom_area_end - h

    return x, y, w, h


def apply_geometry(window, x: int, y: int, w: int, h: int):
    window.resize(w, h)
    window.move(x, y)
