import gi
import signal
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GdkPixbuf, GLib
from pathlib import Path
from panel import NotesPanel

ICON_PATH = Path(__file__).parent / "assets" / "icon.svg"


class NotesApp:
    def __init__(self):
        self.panel = NotesPanel()
        self.panel.hide()
        self._build_tray()

    def _build_tray(self):
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(str(ICON_PATH), 22, 22)
        self.tray = Gtk.StatusIcon()
        self.tray.set_from_pixbuf(pixbuf)
        self.tray.set_tooltip_text("Notes")
        self.tray.set_visible(True)

        # left click → toggle panel
        self.tray.connect("activate", lambda _: self.panel.toggle())
        # right click → menu
        self.tray.connect("popup-menu", self._on_popup_menu)

    def _on_popup_menu(self, icon, button, time):
        menu = Gtk.Menu()
        item_quit = Gtk.MenuItem(label="Stop service")
        item_quit.connect("activate", lambda _: Gtk.main_quit())
        menu.append(item_quit)
        menu.show_all()
        menu.popup(None, None, Gtk.StatusIcon.position_menu, icon, button, time)

    def _setup_signals(self):
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGUSR1, self._on_sigusr1)

    def _on_sigusr1(self):
        self.panel.toggle()
        return GLib.SOURCE_CONTINUE

    def run(self):
        self._setup_signals()
        Gtk.main()
