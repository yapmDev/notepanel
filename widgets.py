import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkX11", "3.0")
from gi.repository import Gtk, Gdk, GdkX11, GLib
import notes as notes_mod


class NoteRow(Gtk.ListBoxRow):
    def __init__(self, note: dict, on_delete):
        super().__init__()
        self.note = note
        self.get_style_context().add_class("note-row")

        row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        row_box.set_margin_top(2)
        row_box.set_margin_bottom(2)

        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)

        title = Gtk.Label(label=note["title"], xalign=0)
        title.get_style_context().add_class("note-title")
        title.set_ellipsize(3)
        text_box.pack_start(title, False, False, 0)

        if note["preview"]:
            preview = Gtk.Label(label=note["preview"], xalign=0)
            preview.get_style_context().add_class("note-preview")
            preview.set_ellipsize(3)
            text_box.pack_start(preview, False, False, 0)

        del_btn = Gtk.Button(label="✕")
        del_btn.get_style_context().add_class("row-delete-btn")
        del_btn.set_valign(Gtk.Align.CENTER)
        del_btn.connect("clicked", lambda _: on_delete(note["path"]))

        row_box.pack_start(text_box, True, True, 0)
        row_box.pack_start(del_btn, False, False, 0)

        self.add(row_box)
        self.show_all()


class TrashRow(Gtk.ListBoxRow):
    def __init__(self, note: dict, on_restore, on_delete_permanent):
        super().__init__()
        self.note = note
        self.get_style_context().add_class("note-row")

        row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        row_box.set_margin_top(2)
        row_box.set_margin_bottom(2)

        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)

        title = Gtk.Label(label=note["title"], xalign=0)
        title.get_style_context().add_class("note-title")
        title.set_ellipsize(3)
        text_box.pack_start(title, False, False, 0)

        if note["preview"]:
            preview = Gtk.Label(label=note["preview"], xalign=0)
            preview.get_style_context().add_class("note-preview")
            preview.set_ellipsize(3)
            text_box.pack_start(preview, False, False, 0)

        btn_restore = Gtk.Button(label="↩")
        btn_restore.get_style_context().add_class("row-restore-btn")
        btn_restore.set_tooltip_text("Restore")
        btn_restore.set_valign(Gtk.Align.CENTER)
        btn_restore.connect("clicked", lambda _: on_restore(note["path"]))

        btn_del = Gtk.Button(label="✕")
        btn_del.get_style_context().add_class("row-delete-btn")
        btn_del.set_tooltip_text("Delete permanently")
        btn_del.set_valign(Gtk.Align.CENTER)
        btn_del.connect("clicked", lambda _: on_delete_permanent(note["path"]))

        row_box.pack_start(text_box, True, True, 0)
        row_box.pack_start(btn_restore, False, False, 0)
        row_box.pack_start(btn_del, False, False, 0)

        self.add(row_box)
        self.show_all()


class QuickCaptureDialog(Gtk.Window):
    def __init__(self):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.set_decorated(False)
        self.set_resizable(True)
        self.set_keep_above(True)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_type_hint(Gdk.WindowTypeHint.DIALOG)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_size_request(460, 220)
        self.set_name("quick-capture")

        self._build_ui()
        self._paste_clipboard()
        self.connect("key-press-event", self._on_key_press)
        self.connect("map-event", self._on_map)

    def _build_ui(self):
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)

        self.text_view = Gtk.TextView()
        self.text_view.set_name("capture-text")
        self.text_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        scroll.add(self.text_view)

        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        bar.set_name("capture-bar")

        hint = Gtk.Label(label="Ctrl+Enter para guardar · Esc para cancelar")
        hint.set_name("capture-hint")
        hint.set_halign(Gtk.Align.START)

        btn_save = Gtk.Button(label="Guardar")
        btn_save.set_name("btn-new")
        btn_save.connect("clicked", self._on_save)

        bar.pack_start(hint, True, True, 0)
        bar.pack_end(btn_save, False, False, 0)

        root.pack_start(scroll, True, True, 0)
        root.pack_start(bar, False, False, 0)

        self.add(root)

    def _on_map(self, widget, event):
        GLib.idle_add(self._request_focus)
        return False

    def _request_focus(self):
        gdk_win = self.get_window()
        if gdk_win:
            try:
                ts = GdkX11.x11_get_server_time(gdk_win)
            except Exception:
                ts = Gdk.CURRENT_TIME
            gdk_win.focus(ts)
        self.text_view.grab_focus()

    def _paste_clipboard(self):
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        text = clipboard.wait_for_text() or ""
        buf = self.text_view.get_buffer()
        buf.set_text(text)
        buf.place_cursor(buf.get_end_iter())

    def _on_key_press(self, widget, event):
        if event.keyval == Gdk.KEY_Escape:
            self.destroy()
            return True
        if event.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            mods = event.state & Gtk.accelerator_get_default_mod_mask()
            if mods == Gdk.ModifierType.CONTROL_MASK:
                self._on_save(None)
                return True
        return False

    def _on_save(self, _btn):
        buf = self.text_view.get_buffer()
        content = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False).strip()
        if content:
            lines = content.splitlines()
            title = lines[0].lstrip("# ").strip() if lines else "Untitled"
            notes_mod.save_note(None, title, content)
        self.destroy()
