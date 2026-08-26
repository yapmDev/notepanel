import gi
import os
import shutil
import signal
gi.require_version("Gtk", "3.0")
gi.require_version("AyatanaAppIndicator3", "0.1")
from gi.repository import Gtk, GLib, AyatanaAppIndicator3 as AppIndicator
from pathlib import Path
from panel import NotesPanel

ICON_NAME = "notepanel-symbolic"
ICON_SOURCE = Path(__file__).parent / "assets" / f"{ICON_NAME}.svg"
ICON_THEME_ROOT = Path.home() / ".local/share/icons/hicolor"
ICON_INSTALL_DIR = ICON_THEME_ROOT / "scalable/status"


class NotesApp:
    def __init__(self):
        self.panel = NotesPanel()
        self.panel.hide()
        self._build_tray()

    def _install_icon(self):
        # The shell only recolors a tray icon it can look up *by name* in an icon
        # theme, so the symbolic SVG has to be installed into hicolor — passing
        # it by path (set_icon_theme_path) yields a plain file icon that stays
        # whatever color the file happens to be.
        target = ICON_INSTALL_DIR / ICON_SOURCE.name
        if target.exists() and target.read_bytes() == ICON_SOURCE.read_bytes():
            return
        ICON_INSTALL_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ICON_SOURCE, target)
        # GTK trusts hicolor/icon-theme.cache over the directory whenever the
        # cache is newer than the theme root, and writing into a subdirectory
        # does not touch that root — so a stale cache would hide the icon.
        os.utime(ICON_THEME_ROOT)
        Gtk.IconTheme.get_default().rescan_if_needed()

    def _build_tray(self):
        self._install_icon()
        self.tray = AppIndicator.Indicator.new(
            "notepanel", ICON_NAME, AppIndicator.IndicatorCategory.APPLICATION_STATUS
        )
        self.tray.set_status(AppIndicator.IndicatorStatus.ACTIVE)
        self.tray.set_title("Notes")

        # left or right click → menu (libayatana exports no Activate method, so
        # the shell has nothing to bind a plain click to)
        menu = Gtk.Menu()
        item_open = Gtk.MenuItem(label="Open notes")
        item_open.connect("activate", lambda _: self.panel.toggle())
        menu.append(item_open)
        menu.append(Gtk.SeparatorMenuItem())
        item_quit = Gtk.MenuItem(label="Stop service")
        item_quit.connect("activate", lambda _: Gtk.main_quit())
        menu.append(item_quit)
        menu.show_all()
        self.tray.set_menu(menu)

        # middle click → toggle straight away, skipping the menu
        self.tray.set_secondary_activate_target(item_open)

    def _setup_signals(self):
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGUSR1, self._on_sigusr1)

    def _on_sigusr1(self):
        self.panel.toggle()
        return GLib.SOURCE_CONTINUE

    def run(self):
        self._setup_signals()
        Gtk.main()
