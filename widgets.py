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


def _preview_row(note: dict, *actions: Gtk.Widget, lines: int = 2) -> Gtk.Box:
    """The row's second line: up to `lines` lines of body preview, with any
    actions passed here pinned to its right.

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
        preview.set_lines(lines)
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


def _connect_hover(on_hover, *sources: Gtk.Widget):
    """Call `on_hover(True)` when the pointer enters any of `sources` and
    `on_hover(False)` once it has left all of them. Each source must be a
    widget with a window of its own, which is the only thing crossing events
    are delivered to.

    More than one source, because a window *inside* another one is not the
    only way GTK stacks them: an event box with no visible window of its own
    leaves its children parented where its own window would have been, so the
    button on a card is a sibling of the card's input-only window rather than
    a child of it. Moving onto that button then reads as a plain leave of the
    card and not as the INFERIOR crossing below — a reveal hung off it takes
    the button out from under the pointer that came for it. Listening on the
    button as well closes the hole from the other side: the pointer is inside
    the group until every member of it has been left, whichever one it leaves
    the group through.

    Only the transitions are passed on. X sends a crossing event whenever the
    stack of windows under the pointer changes, so "still hovering" can arrive
    many times over, and what hangs off this is not free.
    """
    inside = set()
    hovering = False

    def set_hovering(now):
        nonlocal hovering
        if now != hovering:
            hovering = now
            on_hover(now)

    def on_enter(widget, _event):
        inside.add(widget)
        set_hovering(True)
        return False

    def on_leave(widget, event):
        # INFERIOR means the pointer only crossed into a child of this source —
        # a button inside a real event box window — and has not actually left.
        if event.detail != Gdk.NotifyType.INFERIOR:
            inside.discard(widget)
            set_hovering(bool(inside))
        return False

    for source in sources:
        source.connect("enter-notify-event", on_enter)
        source.connect("leave-notify-event", on_leave)


def _hover_reveal(content: Gtk.Widget, button: Gtk.Button) -> Gtk.EventBox:
    """Wrap `content` in the window the reveal needs: a GtkListBoxRow has none
    of its own, so it gets no crossing events to hang the reveal off."""
    event_box = Gtk.EventBox()
    event_box.add(content)
    _connect_hover(lambda hovering: button.show() if hovering else button.hide(), event_box)
    return event_box


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

        self.add(_hover_reveal(row_box, self.remove_btn))
        self.show_all()
        # set after show_all() so the label inside keeps its visible flag;
        # no_show_all only needs to stop future show_all() calls from
        # re-revealing the button itself
        self.remove_btn.set_no_show_all(True)
        self.remove_btn.hide()


class _Card(Gtk.EventBox):
    """What a grid card is, before it is a note's or a trashed note's.

    Not a GtkFlowBoxChild, because a flow box gives every cell in a line the
    height of the tallest one — an empty note next to a long one leaves the
    hole the grid is meant not to have. Cards are dealt into plain column
    boxes instead (panel._layout_grid), so the widget has to bring for itself
    what a cell container would have given it: a window to get the pointer
    and the click that opens the note, which a flow box would have delivered
    as `child-activated`.

    That window is all the event box is for. **It is not the card**: GtkEventBox
    predates GTK's CSS box model and honours neither padding nor margin, so a
    card painted on it would have its text against its own edge and its
    neighbour against its side. The painted card is `self.card`, the GtkBox
    inside it, which does implement the box model — which is also why anything
    that depends on the pointer (hover, focus) has to put its styling on that
    box by hand, the states being the event box's.

    The body preview gets six lines here against the row's two: a cell is a
    fraction of the panel's width, so a line of it holds a fraction of the
    text, and with heights free to differ there is no cost to a long note
    taking the room it needs.
    """

    PREVIEW_LINES = 6

    def __init__(self, note: dict, on_open):
        super().__init__()
        self.note = note
        self._on_open = on_open
        self.set_visible_window(False)
        # A list row is activated by a single click and answers Enter once
        # focused; a card has to arrange both for itself.
        self.set_can_focus(True)
        self.connect("button-press-event", self._on_button_press)
        self.connect("key-press-event", self._on_key_press)
        self.connect("focus-in-event", self._on_focus_change, True)
        self.connect("focus-out-event", self._on_focus_change, False)

        self.card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.card.get_style_context().add_class("note-row")
        self.card.get_style_context().add_class("note-card")
        self.add(self.card)

    def _fill(self, *actions: Gtk.Widget, show_tag: bool = True):
        """Pack the two stacked lines, with `actions` at the end of the first."""
        self.card.pack_start(_title_row(self.note, *actions, show_tag=show_tag), False, False, 0)
        self.card.pack_start(_preview_row(self.note, lines=self.PREVIEW_LINES), False, False, 0)

    def _on_button_press(self, _widget, event):
        # The action chips have windows of their own and swallow their own
        # presses, so a click that reaches here is a click on the card.
        if event.type == Gdk.EventType.BUTTON_PRESS and event.button == 1:
            self._on_open(self.note)
            return True
        return False

    def _on_key_press(self, _widget, event):
        if event.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter, Gdk.KEY_space):
            self._on_open(self.note)
            return True
        return False

    def _on_focus_change(self, _widget, _event, focused):
        context = self.card.get_style_context()
        if focused:
            context.add_class("focused")
        else:
            context.remove_class("focused")
        return False


class NoteCard(_Card):
    """NoteRow's grid counterpart: the same note, as a card only as tall as
    its own text, with the same remove revealed by the pointer.

    Remove is an icon here rather than the row's "Remove" label: it shares the
    title line with a title that has half the width to be read in.
    """

    def __init__(self, note: dict, on_delete, on_open, show_tag: bool = True):
        super().__init__(note, on_open)
        self._on_delete = on_delete

        self.remove_btn = _icon_button("edit-delete-symbolic", "row-remove-btn")
        self.remove_btn.set_tooltip_text("Remove")
        self.remove_btn.connect("clicked", self._on_remove_clicked)

        self._fill(self.remove_btn, show_tag=show_tag)
        _connect_hover(self._set_hovering, self, self.remove_btn)
        self.show_all()
        # The chip keeps its place whether it is up or not, and only its paint
        # comes and goes. Showing and hiding it would re-request the card's
        # size, and in a grid that means re-measuring a whole column of
        # wrapped previews — 26ms of it, on every crossing, i.e. a stall for
        # every card the pointer sweeps over. Opacity costs nothing but the
        # pixels — and not set_sensitive() either, whose state change
        # invalidates the style and so costs exactly as much as the show() did.
        self._set_hovering(False)

    def _on_remove_clicked(self, _button):
        # The chip holds its place while transparent, so a click can only land
        # on it with the pointer over the card — which is when it is up. This
        # covers the gap: the press that arrives between leaving and repainting.
        if self.remove_btn.get_opacity():
            self._on_delete(self.note["path"])

    def _set_hovering(self, hovering: bool):
        self.remove_btn.set_opacity(1 if hovering else 0)
        # The pointer is over the event box, not the painted card inside it,
        # so that card never reaches `:hover` on its own. `.hover` is the same
        # paint as a class, and a colour change is a redraw, not a resize.
        context = self.card.get_style_context()
        if hovering:
            context.add_class("hover")
        else:
            context.remove_class("hover")


class TrashCard(_Card):
    """TrashRow's grid counterpart, and NoteCard's trashed one.

    No hover to it: its two actions are permanent, the way they are in the
    trash row, a trashed note being nothing but those two decisions. That also
    makes it the cheap card — with nothing appearing on hover, nothing ever
    re-requests its size.

    The tag prefix always shows, as it does in the trash row: the trash has no
    filter of its own, so there is no dropdown already saying what it says.
    """

    def __init__(self, note: dict, on_restore, on_delete_permanent, on_open):
        super().__init__(note, on_open)

        btn_restore = Gtk.Button(label="\u21a9")
        btn_restore.get_style_context().add_class("row-restore-btn")
        btn_restore.set_tooltip_text("Restore")
        btn_restore.connect("clicked", lambda _: on_restore(note["path"]))

        btn_del = _icon_button("edit-delete-symbolic", "row-delete-btn")
        btn_del.set_tooltip_text("Delete permanently")
        btn_del.connect("clicked", lambda _: on_delete_permanent(note["path"]))

        self._fill(btn_restore, btn_del)
        self.show_all()


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
