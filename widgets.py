import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkX11", "3.0")
from gi.repository import Gtk, Gdk, GdkX11, GLib
import notes as notes_mod
import settings as settings_mod

CORNER_LABELS = {
    "top-right": "Top right",
    "top-left": "Top left",
    "bottom-right": "Bottom right",
    "bottom-left": "Bottom left",
    "center": "Center",
}


def _title_row(note: dict) -> Gtk.Box:
    """`Title · tag` — the tag is never shown inside the note itself, so the
    list is the only place it's visible.

    Nothing expands here: both labels hug the left so the tag sits right where
    the title text ends. Letting the title fill the row instead would push the
    tag against the right edge, which is exactly where the delete button
    appears on hover.
    """
    box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)

    title = Gtk.Label(label=note["title"], xalign=0)
    title.get_style_context().add_class("note-title")
    title.set_valign(Gtk.Align.BASELINE)
    title.set_ellipsize(3)
    # The title is still what gives way when the row runs out of width: an
    # ellipsized label's minimum width is far below the tag's natural one.
    box.pack_start(title, False, False, 0)

    if note.get("tag"):
        dot = Gtk.Label(label="·")
        dot.get_style_context().add_class("note-tag-dot")
        dot.set_valign(Gtk.Align.BASELINE)
        box.pack_start(dot, False, False, 0)

        tag = Gtk.Label(label=note["tag"], xalign=0)
        tag.get_style_context().add_class("note-tag")
        tag.set_valign(Gtk.Align.BASELINE)
        tag.set_ellipsize(3)
        tag.set_max_width_chars(14)
        box.pack_start(tag, False, False, 0)

    return box


class NoteRow(Gtk.ListBoxRow):
    def __init__(self, note: dict, on_delete):
        super().__init__()
        self.note = note
        self.get_style_context().add_class("note-row")

        row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        row_box.set_margin_top(2)
        row_box.set_margin_bottom(2)

        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        text_box.pack_start(_title_row(note), False, False, 0)

        if note["preview"]:
            preview = Gtk.Label(label=note["preview"], xalign=0)
            preview.get_style_context().add_class("note-preview")
            preview.set_ellipsize(3)
            text_box.pack_start(preview, False, False, 0)

        del_icon_box = Gtk.Box()
        del_icon_box.pack_start(
            Gtk.Image.new_from_icon_name("user-trash-symbolic", Gtk.IconSize.SMALL_TOOLBAR),
            True, True, 0,
        )

        self.del_btn = Gtk.Button()
        self.del_btn.add(del_icon_box)
        self.del_btn.get_style_context().add_class("row-delete-btn")
        self.del_btn.set_valign(Gtk.Align.CENTER)
        self.del_btn.connect("clicked", lambda _: on_delete(note["path"]))

        row_box.pack_start(text_box, True, True, 0)
        row_box.pack_start(self.del_btn, False, False, 0)

        event_box = Gtk.EventBox()
        event_box.add(row_box)
        event_box.connect("enter-notify-event", self._on_enter)
        event_box.connect("leave-notify-event", self._on_leave)

        self.add(event_box)
        self.show_all()
        # set after show_all() so the icon inside keeps its visible flag;
        # no_show_all only needs to stop future show_all() calls from
        # re-revealing the button itself
        self.del_btn.set_no_show_all(True)
        self.del_btn.hide()

    def _on_enter(self, widget, event):
        self.del_btn.show()
        return False

    def _on_leave(self, widget, event):
        if event.detail != Gdk.NotifyType.INFERIOR:
            self.del_btn.hide()
        return False


class TrashRow(Gtk.ListBoxRow):
    def __init__(self, note: dict, on_restore, on_delete_permanent):
        super().__init__()
        self.note = note
        self.get_style_context().add_class("note-row")

        row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        row_box.set_margin_top(2)
        row_box.set_margin_bottom(2)

        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        text_box.pack_start(_title_row(note), False, False, 0)

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

        del_icon_box = Gtk.Box()
        del_icon_box.pack_start(
            Gtk.Image.new_from_icon_name("edit-delete-symbolic", Gtk.IconSize.SMALL_TOOLBAR),
            True, True, 0,
        )

        btn_del = Gtk.Button()
        btn_del.add(del_icon_box)
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
            # A capture is all body. Deriving a title line instead of
            # promoting the first line out of the note is what keeps the
            # captured text intact — the header line is hidden in the editor.
            first = next((line.strip() for line in content.splitlines() if line.strip()), "")
            notes_mod.save_note(None, first[:60], "", content)
        self.destroy()


class SettingsDialog(Gtk.Window):
    def __init__(self, on_change, on_reset_geometry=None):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self._on_change_cb = on_change
        self._on_reset_geometry_cb = on_reset_geometry
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_keep_above(True)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_type_hint(Gdk.WindowTypeHint.DIALOG)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_name("settings-dialog")

        self._prefs = settings_mod.load_settings()
        self._build_ui()
        self.connect("key-press-event", self._on_key_press)

    def _build_ui(self):
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        root.set_name("settings-body")

        title = Gtk.Label(label="Panel settings", xalign=0)
        title.set_name("settings-title")
        root.pack_start(title, False, False, 0)

        corner_label = Gtk.Label(label="Corner", xalign=0)
        corner_label.set_name("settings-label")
        self.corner_combo = Gtk.ComboBoxText()
        for corner_id in settings_mod.CORNERS:
            self.corner_combo.append(corner_id, CORNER_LABELS[corner_id])
        self.corner_combo.set_active_id(self._prefs["corner"])
        self.corner_combo.connect("changed", self._on_corner_changed)

        width_label = Gtk.Label(label="Width (%)", xalign=0)
        width_label.set_name("settings-label")
        self.width_spin = Gtk.SpinButton.new_with_range(1, 100, 1)
        self.width_spin.set_value(self._prefs["width_percent"])
        self._wire_spin(self.width_spin, "width_percent")

        height_label = Gtk.Label(label="Height (%)", xalign=0)
        height_label.set_name("settings-label")
        self.height_spin = Gtk.SpinButton.new_with_range(1, 100, 1)
        self.height_spin.set_value(self._prefs["height_percent"])
        self._wire_spin(self.height_spin, "height_percent")

        remember_label = Gtk.Label(label="Reopen last note (min)", xalign=0)
        remember_label.set_name("settings-label")
        self.remember_spin = Gtk.SpinButton.new_with_range(
            0, settings_mod.MAX_REMEMBER_NOTE_MINUTES, 1
        )
        self.remember_spin.set_value(self._prefs["remember_note_minutes"])
        self._wire_spin(self.remember_spin, "remember_note_minutes")

        remember_hint = Gtk.Label(
            label="Reopening the panel jumps back into the last note if it was\n"
                  "used within this window. 0 always opens the notes list.",
            xalign=0,
        )
        remember_hint.set_name("settings-hint")

        grid = Gtk.Grid(row_spacing=8, column_spacing=12)
        grid.attach(corner_label, 0, 0, 1, 1)
        grid.attach(self.corner_combo, 1, 0, 1, 1)
        grid.attach(width_label, 0, 1, 1, 1)
        grid.attach(self.width_spin, 1, 1, 1, 1)
        grid.attach(height_label, 0, 2, 1, 1)
        grid.attach(self.height_spin, 1, 2, 1, 1)
        grid.attach(remember_label, 0, 3, 1, 1)
        grid.attach(self.remember_spin, 1, 3, 1, 1)
        grid.attach(remember_hint, 0, 4, 2, 1)
        root.pack_start(grid, False, False, 0)

        self.hide_on_focus_out_check = Gtk.CheckButton(label="Hide panel when it loses focus")
        self.hide_on_focus_out_check.set_active(self._prefs["hide_on_focus_out"])
        self.hide_on_focus_out_check.connect("toggled", self._on_hide_on_focus_out_toggled)
        root.pack_start(self.hide_on_focus_out_check, False, False, 0)

        btn_reset_geometry = Gtk.Button(label="Reset position and size to default")
        btn_reset_geometry.set_name("btn-back")
        btn_reset_geometry.connect("clicked", self._on_reset_geometry)
        root.pack_start(btn_reset_geometry, False, False, 0)

        self.add(root)

    def _on_key_press(self, widget, event):
        if event.keyval == Gdk.KEY_Escape:
            self.destroy()
            return True
        return False

    def _apply_setting(self, key, value):
        new_settings = {**settings_mod.load_settings(), key: value}
        settings_mod.save_settings(new_settings)
        if self._on_change_cb:
            self._on_change_cb(new_settings, key)

    def _on_corner_changed(self, combo):
        self._apply_setting("corner", combo.get_active_id() or settings_mod.DEFAULTS["corner"])

    def _wire_spin(self, spin, key):
        # Steppers (+/-, scroll, Up/Down keys) are single discrete edits and
        # apply live. Typing free text is not: intermediate keystrokes (e.g.
        # "5" while typing "50") shouldn't take effect mid-edit, so those only
        # commit on Enter or when the field loses focus.
        state = {"editing": False}

        def commit():
            if state["editing"]:
                state["editing"] = False
                self._apply_setting(key, int(spin.get_value()))

        def on_key_press(widget, event):
            stepper_keys = (
                Gdk.KEY_Up, Gdk.KEY_Down, Gdk.KEY_Page_Up, Gdk.KEY_Page_Down,
                Gdk.KEY_Tab, Gdk.KEY_ISO_Left_Tab, Gdk.KEY_Escape,
            )
            if event.keyval not in stepper_keys:
                state["editing"] = True
            return False

        def on_value_changed(widget):
            if not state["editing"]:
                self._apply_setting(key, int(widget.get_value()))

        def on_focus_out(widget, event):
            commit()
            return False

        def on_activate(widget):
            commit()

        spin.connect("key-press-event", on_key_press)
        spin.connect("value-changed", on_value_changed)
        spin.connect("focus-out-event", on_focus_out)
        spin.connect("activate", on_activate)

    def _on_hide_on_focus_out_toggled(self, check):
        self._apply_setting("hide_on_focus_out", check.get_active())

    def _on_reset_geometry(self, _btn):
        if self._on_reset_geometry_cb:
            self._on_reset_geometry_cb()
        self._prefs = settings_mod.load_settings()
        self.corner_combo.set_active_id(self._prefs["corner"])
        self.width_spin.set_value(self._prefs["width_percent"])
        self.height_spin.set_value(self._prefs["height_percent"])
