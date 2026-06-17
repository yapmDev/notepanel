import gi
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk

PANEL_WIDTH_RATIO = 0.20


def get_target_geometry() -> tuple[int, int, int, int]:
    display = Gdk.Display.get_default()
    monitor = display.get_primary_monitor() or display.get_monitor(0)
    geo = monitor.get_geometry()
    work = monitor.get_workarea()
    w = int(geo.width * PANEL_WIDTH_RATIO)
    h = work.height if work.height > 0 else geo.height
    y = work.y if work.height > 0 else geo.y
    x = geo.x + geo.width - w
    return x, y, w, h


def apply_geometry(window, x: int, y: int, w: int, h: int):
    window.set_size_request(w, h)
    gdk_win = window.get_window()
    if gdk_win:
        gdk_win.move_resize(x, y, w, h)
    else:
        window.resize(w, h)
        window.move(x, y)
