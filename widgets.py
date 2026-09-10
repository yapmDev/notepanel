import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gtk, Gdk, Pango
import settings as settings_mod

CORNER_LABELS = {
    "top-right": "Top right",
    "top-left": "Top left",
    "bottom-right": "Bottom right",
    "bottom-left": "Bottom left",
    "center": "Center",
}


def _title_row(note: dict, *actions: Gtk.Widget, show_tag: bool = True) -> Gtk.Box:
    """`tag : Title              [action]` — the tag is never shown inside the
    note itself, so the list is the only place it's visible.

    The tag leads the line at its natural width and the title takes whatever is
    left, so the titles start at a different x on every row; giving the tag a
    fixed `set_width_chars` would turn that ragged edge into a real column at
    the cost of wasting width on short tags. An untagged note simply has no
    prefix and starts at the row's left edge.

    `show_tag` drops the prefix entirely: with a tag filter active every visible
    row carries the same one, so the prefix would repeat down the whole list
    without telling the reader anything the dropdown isn't already showing.

    Actions are packed at the far end of this line, which is what the tag moving
    to the front frees up.
    """
    box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)

    if show_tag and note.get("tag"):
        # The colon rides on the tag's own label rather than a separator widget
        # of its own — it belongs to the prefix and takes the prefix's colour.
        tag = Gtk.Label(label=f"{note['tag']} :", xalign=0)
        tag.get_style_context().add_class("note-tag")
        tag.set_valign(Gtk.Align.BASELINE)
        tag.set_ellipsize(Pango.EllipsizeMode.END)
        tag.set_max_width_chars(14)
        box.pack_start(tag, False, False, 0)

    title = Gtk.Label(label=note["title"], xalign=0)
    title.get_style_context().add_class("note-title")
    title.set_valign(Gtk.Align.BASELINE)
    title.set_ellipsize(Pango.EllipsizeMode.END)
    box.pack_start(title, True, True, 0)

    # pack_end fills right-to-left, so reverse to have `actions` read
    # left-to-right on screen in the order they were passed.
    for action in reversed(actions):
        action.set_valign(Gtk.Align.CENTER)
        box.pack_end(action, False, False, 0)

    return box


def _preview_row(note: dict, *actions: Gtk.Widget) -> Gtk.Box:
    """The row's second line: up to two lines of body preview, with any actions
    passed here pinned to its right.

    A note with an empty body gets no label at all (an empty one would still
    claim a line's height); actions then sit alone on this line, which keeps
    them in the same place on every row.
    """
    box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)

    if note["preview"]:
        preview = Gtk.Label(label=note["preview"], xalign=0)
        preview.get_style_context().add_class("note-preview")
        # set_lines() only takes effect with wrapping on and an ellipsize mode
        # set; without both, the label falls back to a single unbounded line.
        preview.set_line_wrap(True)
        preview.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        preview.set_lines(2)
        preview.set_ellipsize(Pango.EllipsizeMode.END)
        preview.set_valign(Gtk.Align.START)
        box.pack_start(preview, True, True, 0)

    for action in reversed(actions):
        action.set_valign(Gtk.Align.CENTER)
        box.pack_end(action, False, False, 0)

    return box


def _icon_button(icon_name: str, css_class: str) -> Gtk.Button:
    icon_box = Gtk.Box()
    icon_box.pack_start(
        Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.SMALL_TOOLBAR),
        True, True, 0,
    )
    button = Gtk.Button()
    button.add(icon_box)
    button.get_style_context().add_class(css_class)
    return button


class NoteRow(Gtk.ListBoxRow):
    def __init__(self, note: dict, on_delete, show_tag: bool = True):
        super().__init__()
        self.note = note
        self.get_style_context().add_class("note-row")

        row_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        row_box.set_margin_top(2)
        row_box.set_margin_bottom(2)

        self.remove_btn = Gtk.Button(label="Remove")
        self.remove_btn.get_style_context().add_class("row-remove-btn")
        self.remove_btn.connect("clicked", lambda _: on_delete(note["path"]))

        row_box.pack_start(_title_row(note, self.remove_btn, show_tag=show_tag), False, False, 0)
        row_box.pack_start(_preview_row(note), False, False, 0)

        # The row itself gets no enter/leave events — GtkListBoxRow has no
        # window of its own to receive them — so the hover reveal hangs off an
        # EventBox wrapping the content.
        event_box = Gtk.EventBox()
        event_box.add(row_box)
        event_box.connect("enter-notify-event", self._on_enter)
        event_box.connect("leave-notify-event", self._on_leave)

        self.add(event_box)
        self.show_all()
        # set after show_all() so the label inside keeps its visible flag;
        # no_show_all only needs to stop future show_all() calls from
        # re-revealing the button itself
        self.remove_btn.set_no_show_all(True)
        self.remove_btn.hide()

    def _on_enter(self, widget, event):
        self.remove_btn.show()
        return False

    def _on_leave(self, widget, event):
        # INFERIOR means the pointer only crossed into a child of the row —
        # the button itself, most of the time — and has not actually left.
        if event.detail != Gdk.NotifyType.INFERIOR:
            self.remove_btn.hide()
        return False


class TrashRow(Gtk.ListBoxRow):
    def __init__(self, note: dict, on_restore, on_delete_permanent):
        super().__init__()
        self.note = note
        self.get_style_context().add_class("note-row")

        row_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        row_box.set_margin_top(2)
        row_box.set_margin_bottom(2)

        btn_restore = Gtk.Button(label="\u21a9")
        btn_restore.get_style_context().add_class("row-restore-btn")
        btn_restore.set_tooltip_text("Restore")
        btn_restore.connect("clicked", lambda _: on_restore(note["path"]))

        btn_del = _icon_button("edit-delete-symbolic", "row-delete-btn")
        btn_del.set_tooltip_text("Delete permanently")
        btn_del.connect("clicked", lambda _: on_delete_permanent(note["path"]))

        row_box.pack_start(_title_row(note), False, False, 0)
        row_box.pack_start(_preview_row(note, btn_restore, btn_del), False, False, 0)

        self.add(row_box)
        self.show_all()


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
