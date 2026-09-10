import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkX11", "3.0")
gi.require_version("WebKit2", "4.1")
from gi.repository import Gtk, Gdk, GdkX11, GLib, WebKit2
from pathlib import Path
import time
import notes as notes_mod
import preview as preview_mod
import geometry as geometry_mod
import settings as settings_mod
from undo import UndoStack
from widgets import NoteRow, TrashRow, SettingsDialog

# Ids for the two tag-filter entries that aren't tags themselves. Uppercase is
# what keeps them from colliding with a real tag: notes.normalize_tag()
# lowercases every tag, so neither can ever be one. (A NUL-prefixed sentinel
# would look safer and isn't — GTK truncates ids at the first NUL, collapsing
# both of these to the same empty string.)
_TAG_ALL = "ALL"
_TAG_NONE = "NONE"

# What the editor's tag combo shows for a note with no tag. Only ever text on
# screen: it maps back to "" on save, so an untagged note stays in the one
# untagged group (_TAG_NONE) instead of spawning a real tag that reads the same.
_UNTAGGED_TEXT = "untagged"


def _default_note_title() -> str:
    """The title a new note carries until it's edited."""
    return time.strftime("New Note Title %Y-%m-%d %H:%M:%S")


class NotesPanel(Gtk.Window):
    def __init__(self):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.set_name("panel-root")
        self.set_title("Notes")
        self.set_decorated(True)
        self.set_resizable(True)
        self.set_type_hint(Gdk.WindowTypeHint.NORMAL)

        self._current_path: Path | None = None
        # The untouched default title of a new note, if that's what the entry
        # still holds — an empty note under it is not worth a file yet.
        self._default_title: str | None = None
        self._save_timeout: int | None = None
        self._notes: list[dict] = []
        self._pending_position = False
        self._hidden_at: float = 0.0
        self._focus_lost_at: float = 0.0
        self._hide_timeout: int | None = None
        self._trash_mode = False
        # None = every tag, "" = only untagged, otherwise that one tag.
        self._tag_filter: str | None = None
        self._tag_filter_items: list[tuple[str, int]] = []
        self._tag_choices: list[str] = []
        self._suppress_tag_filter = False
        self._suppress_meta_save = False

        self._load_css()
        self._build_ui()
        self._refresh_notes()
        self._restore_last_note()
        self._position_panel()

        self.connect("key-press-event", self._on_key_press)
        self.connect("map-event", self._on_map_event)
        self.connect("delete-event", self._on_delete_event)
        self.connect("focus-out-event", self._on_focus_out)
        self.connect("focus-in-event", self._on_focus_in)

    def _load_css(self):
        css_path = Path(__file__).parent / "style.css"
        provider = Gtk.CssProvider()
        provider.load_from_path(str(css_path))
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    def _build_ui(self):
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        root.set_name("panel-root")

        # The search row and the bottom bar belong to the list view only, and
        # are hidden while the editor is up — no_show_all so the panel's
        # show_all() on every toggle can't override the current view's state.
        search_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        search_box.set_name("toolbar")
        search_box.set_no_show_all(True)
        self.search_box = search_box
        self.search = Gtk.SearchEntry()
        self.search.set_name("search-entry")
        self.search.set_placeholder_text("Search notes...")
        self.search.set_halign(Gtk.Align.FILL)
        self.search.connect("search-changed", self._on_search)
        search_box.set_center_widget(self.search)

        # Sits in the search row, left of the (centered) entry. Rebuilt from
        # the tags actually in use — see _sync_tag_filter().
        self.tag_filter = Gtk.ComboBoxText()
        self.tag_filter.set_name("tag-filter")
        self.tag_filter.set_tooltip_text("Filter by tag")
        self.tag_filter.set_valign(Gtk.Align.CENTER)
        self.tag_filter.connect("changed", self._on_tag_filter_changed)
        search_box.pack_start(self.tag_filter, False, False, 0)

        # Sits in the search row, to the right of the (centered) entry. Shown
        # only when the list has results — no_show_all so the panel's show_all()
        # can't override the hidden state set by _refresh_notes/_refresh_trash.
        self.status_label = Gtk.Label(label="", xalign=1)
        self.status_label.set_name("status-label")
        self.status_label.set_no_show_all(True)
        search_box.pack_end(self.status_label, False, False, 0)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)

        self.list_box = Gtk.ListBox()
        self.list_box.set_name("note-list")
        self.list_box.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.list_box.connect("row-activated", self._on_row_activated)
        scroll.add(self.list_box)

        editor_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        editor_box.set_name("editor-box")
        editor_box.set_vexpand(True)

        # The editor's own actions live in the shared bottom bar (built below),
        # next to the same "← Back" button the trash uses.
        self.btn_copy = Gtk.Button.new_from_icon_name("edit-copy-symbolic", Gtk.IconSize.SMALL_TOOLBAR)
        self.btn_copy.set_name("btn-action")
        self.btn_copy.set_tooltip_text("Copy")
        self.btn_copy.connect("clicked", self._on_copy)

        self.btn_select_all = Gtk.Button.new_from_icon_name("edit-select-all-symbolic", Gtk.IconSize.SMALL_TOOLBAR)
        self.btn_select_all.set_name("btn-action")
        self.btn_select_all.set_tooltip_text("Select all")
        self.btn_select_all.connect("clicked", self._on_select_all)

        self.btn_find = Gtk.Button.new_from_icon_name("edit-find-symbolic", Gtk.IconSize.SMALL_TOOLBAR)
        self.btn_find.set_name("btn-action")
        self.btn_find.set_tooltip_text("Find in note")
        self.btn_find.connect("clicked", self._on_toggle_find)

        self._preview_mode = False
        self.btn_preview = Gtk.Button.new_from_icon_name("view-reveal-symbolic", Gtk.IconSize.SMALL_TOOLBAR)
        self.btn_preview.set_name("btn-action")
        self.btn_preview.set_tooltip_text("Preview")
        self.btn_preview.connect("clicked", self._on_toggle_preview)

        find_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        find_bar.set_name("find-bar")

        self.find_entry = Gtk.SearchEntry()
        self.find_entry.set_name("find-entry")
        self.find_entry.set_placeholder_text("Find in note...")
        self.find_entry.set_hexpand(True)
        self.find_entry.connect("search-changed", self._on_find_changed)
        self.find_entry.connect("activate", self._on_find_next)
        self.find_entry.connect("key-press-event", self._on_find_key_press)

        self.find_count_label = Gtk.Label(label="", xalign=0)
        self.find_count_label.set_name("find-count")

        btn_find_prev = Gtk.Button.new_from_icon_name("go-up-symbolic", Gtk.IconSize.SMALL_TOOLBAR)
        btn_find_prev.set_name("btn-action")
        btn_find_prev.set_tooltip_text("Previous match")
        btn_find_prev.connect("clicked", self._on_find_prev)

        btn_find_next = Gtk.Button.new_from_icon_name("go-down-symbolic", Gtk.IconSize.SMALL_TOOLBAR)
        btn_find_next.set_name("btn-action")
        btn_find_next.set_tooltip_text("Next match")
        btn_find_next.connect("clicked", self._on_find_next)

        btn_find_close = Gtk.Button.new_from_icon_name("window-close-symbolic", Gtk.IconSize.SMALL_TOOLBAR)
        btn_find_close.set_name("btn-action")
        btn_find_close.set_tooltip_text("Close")
        btn_find_close.connect("clicked", self._on_toggle_find)

        find_bar.pack_start(self.find_entry, True, True, 0)
        find_bar.pack_start(self.find_count_label, False, False, 0)
        find_bar.pack_start(btn_find_prev, False, False, 0)
        find_bar.pack_start(btn_find_next, False, False, 0)
        find_bar.pack_start(btn_find_close, False, False, 0)

        self.find_revealer = Gtk.Revealer()
        # Slides up from the bottom of the editor, right above the bar holding
        # the button that opened it.
        self.find_revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_UP)
        self.find_revealer.set_reveal_child(False)
        self.find_revealer.add(find_bar)

        self._find_matches: list[tuple[int, int]] = []
        self._find_index = -1

        self.editor_stack = Gtk.Stack()
        self.editor_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)
        self.editor_stack.set_transition_duration(120)
        self.editor_stack.set_vexpand(True)

        text_scroll = Gtk.ScrolledWindow()
        text_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        text_scroll.set_vexpand(True)

        self.text_view = Gtk.TextView()
        self.text_view.set_name("editor-text")
        self.text_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        text_buf = self.text_view.get_buffer()
        text_buf.connect("changed", self._on_content_changed)
        # GTK 3 gives a text buffer no undo of its own; this records one.
        self.undo_stack = UndoStack(text_buf)
        self.find_tag = text_buf.create_tag("find-match", background="#ffe066", foreground="#000000")
        self.find_tag_current = text_buf.create_tag(
            "find-match-current", background="#ff9800", foreground="#000000"
        )
        text_scroll.add(self.text_view)

        wk_settings = WebKit2.Settings()
        wk_settings.set_enable_javascript(False)
        wk_settings.set_enable_plugins(False)
        self.web_view = WebKit2.WebView.new_with_settings(wk_settings)
        self.web_view.set_vexpand(True)

        self.editor_stack.add_named(text_scroll, "editor")
        self.editor_stack.add_named(self.web_view, "preview")
        self.editor_stack.set_visible_child_name("editor")

        # The note's title and tag live here, not in the buffer: the file
        # still stores them on its first line ("Title :: tag"), but the editor
        # shows only the body, so this row is the only place to edit them.
        # no_show_all so the panel's show_all() can't reveal it over the
        # preview, which renders the title as its own H1 instead.
        meta_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        meta_row.set_name("meta-row")
        meta_row.set_no_show_all(True)
        self.meta_row = meta_row

        self.title_entry = Gtk.Entry()
        self.title_entry.set_name("meta-title")
        self.title_entry.set_placeholder_text("Title")
        self.title_entry.set_hexpand(True)
        self.title_entry.connect("activate", self._on_title_activate)
        self.title_entry.connect("focus-out-event", self._on_meta_focus_out)

        self.tag_combo = Gtk.ComboBoxText.new_with_entry()
        self.tag_combo.set_name("meta-tag")
        self.tag_combo.connect("changed", self._on_tag_combo_changed)
        tag_entry = self.tag_combo.get_child()
        tag_entry.set_name("meta-tag-entry")
        tag_entry.set_placeholder_text("tag")
        tag_entry.set_width_chars(10)
        tag_entry.connect("activate", self._on_tag_activate)
        tag_entry.connect("focus-out-event", self._on_meta_focus_out)

        meta_row.pack_start(self.title_entry, True, True, 0)
        meta_row.pack_start(self.tag_combo, False, False, 0)

        editor_box.pack_start(meta_row, False, False, 0)
        editor_box.pack_start(self.editor_stack, True, True, 0)
        editor_box.pack_start(self.find_revealer, False, False, 0)

        # The list and the editor are separate destinations, not panes sharing
        # the panel's height: only one is on screen at a time.
        self.main_stack = Gtk.Stack()
        self.main_stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.main_stack.set_transition_duration(120)
        self.main_stack.set_vexpand(True)
        self.main_stack.add_named(scroll, "list")
        self.main_stack.add_named(editor_box, "editor")
        # A stack can only switch to a child that is visible itself, and the
        # window's show_all() doesn't run until the first toggle() — show both
        # pages now so switching works before that (e.g. reopening the last
        # note during __init__). The stack still shows only one at a time.
        scroll.show_all()
        editor_box.show_all()
        self.main_stack.set_visible_child_name("list")

        # bottom bar — the single navigation surface: the same "← Back" button
        # for every nested destination (trash, editor), plus that destination's
        # own actions. Membership per mode is decided by _update_bottom_bar().
        bottom_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        bottom_bar.set_name("bottom-bar")
        bottom_bar.set_no_show_all(True)
        self.bottom_bar = bottom_bar

        self.btn_new = Gtk.Button(label="+ New note")
        self.btn_new.set_name("btn-new")
        self.btn_new.connect("clicked", self._on_new_note)

        self.btn_open_trash = Gtk.Button()
        self.btn_open_trash.set_name("btn-action")
        self.btn_open_trash.set_image(
            Gtk.Image.new_from_icon_name("user-trash-symbolic", Gtk.IconSize.SMALL_TOOLBAR)
        )
        self.btn_open_trash.set_tooltip_text("Trash")
        self.btn_open_trash.connect("clicked", self._on_open_trash)

        self.btn_settings = Gtk.Button.new_from_icon_name("emblem-system-symbolic", Gtk.IconSize.SMALL_TOOLBAR)
        self.btn_settings.set_name("btn-action")
        self.btn_settings.set_tooltip_text("Settings")
        self.btn_settings.connect("clicked", self._on_open_settings)

        self.btn_back = Gtk.Button(label="← Back")
        self.btn_back.set_name("btn-back")
        self.btn_back.connect("clicked", self._on_back)

        self.btn_empty_trash = Gtk.Button(label="Empty trash")
        self.btn_empty_trash.set_name("btn-empty-trash")
        self.btn_empty_trash.connect("clicked", self._on_empty_trash)

        # Separates the one control that never changes (settings) from the
        # actions of whichever view is up.
        bar_separator = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        bar_separator.set_name("bar-separator")

        bottom_bar.pack_start(self.btn_back, False, False, 0)
        bottom_bar.pack_start(self.btn_new, True, True, 0)
        # pack_end fills right-to-left, so this lists the end group from its
        # rightmost slot inward: settings keeps the far-right slot in every
        # view, then the separator, then the current view's own actions (only
        # one view's buttons are visible at a time).
        bottom_bar.pack_end(self.btn_settings, False, False, 0)
        bottom_bar.pack_end(bar_separator, False, False, 0)
        bottom_bar.pack_end(self.btn_preview, False, False, 0)
        bottom_bar.pack_end(self.btn_find, False, False, 0)
        bottom_bar.pack_end(self.btn_select_all, False, False, 0)
        bottom_bar.pack_end(self.btn_copy, False, False, 0)
        bottom_bar.pack_end(self.btn_empty_trash, False, False, 0)
        bottom_bar.pack_end(self.btn_open_trash, False, False, 0)

        root.pack_start(search_box, False, False, 0)
        root.pack_start(self.main_stack, True, True, 0)
        root.pack_start(bottom_bar, False, False, 0)

        # search_box/bottom_bar are no_show_all (toggled via show()/hide()),
        # which blocks show_all() from ever reaching their children — show them
        # once here so they're ready whenever their bar becomes visible. That
        # same blocking is what lets _update_bottom_bar() own per-mode
        # visibility from now on: no later show_all() can undo its hides.
        for bar in (search_box, bottom_bar, meta_row):
            for child in bar.get_children():
                child.show_all()

        self.add(root)

    def _position_panel(self):
        self.set_size_request(280, 200)
        x, y, w, h = geometry_mod.get_target_geometry()
        self.resize(w, h)

    def _on_map_event(self, widget, event):
        if self._pending_position:
            self._pending_position = False
            x, y, w, h = geometry_mod.get_target_geometry()
            geometry_mod.apply_geometry(self, x, y, w, h)
            GLib.timeout_add(80, lambda: geometry_mod.apply_geometry(self, x, y, w, h) or False)
        return False

    def _save_geometry(self):
        x, y = self.get_position()
        w, h = self.get_size()
        settings_mod.save_geometry(x, y, w, h)

    def _reset_geometry(self):
        settings_mod.reset_geometry()
        x, y, w, h = geometry_mod.get_target_geometry()
        geometry_mod.apply_geometry(self, x, y, w, h)

    def _refresh_notes(self, query: str = ""):
        # Before the query runs: the dropdown may drop the tag being filtered
        # on (the last note carrying it just lost it), which resets the filter.
        self._sync_tag_filter()

        for row in self.list_box.get_children():
            self.list_box.remove(row)

        if query:
            self._notes = notes_mod.search_notes(query, self._tag_filter)
        else:
            self._notes = notes_mod.list_notes(self._tag_filter)

        # `None` is the All filter — the only view where the rows carry more
        # than one tag between them, so the only one where the `tag :` prefix
        # on each row says anything the dropdown isn't already saying.
        show_tag = self._tag_filter is None
        for note in self._notes:
            self.list_box.add(NoteRow(note, self._delete_note_by_path, show_tag=show_tag))

        self._set_status_count(len(self._notes))

    # --- tags ---

    def _sync_tag_filter(self):
        """Rebuild the tag dropdown, but only when the tags in use changed.

        _refresh_notes() runs on every save, and rebuilding the model each
        time would close the popup mid-click and churn the selection.
        """
        items = notes_mod.list_tags()
        if items == self._tag_filter_items:
            return
        self._tag_filter_items = items

        self._suppress_tag_filter = True
        self.tag_filter.remove_all()
        self.tag_filter.append(_TAG_ALL, "All")
        for tag, count in items:
            if tag:
                self.tag_filter.append(tag, f"{tag} ({count})")
            else:
                self.tag_filter.append(_TAG_NONE, f"Untagged ({count})")
        if not self.tag_filter.set_active_id(self._filter_id()):
            # The filtered tag is gone from every note — fall back to All.
            self._tag_filter = None
            self.tag_filter.set_active_id(_TAG_ALL)
        self._suppress_tag_filter = False

    def _filter_id(self) -> str:
        if self._tag_filter is None:
            return _TAG_ALL
        return _TAG_NONE if self._tag_filter == "" else self._tag_filter

    def _on_tag_filter_changed(self, combo):
        if self._suppress_tag_filter:
            return
        active_id = combo.get_active_id()
        if active_id == _TAG_ALL:
            self._tag_filter = None
        elif active_id == _TAG_NONE:
            self._tag_filter = ""
        else:
            self._tag_filter = active_id
        self._refresh_notes(self.search.get_text())

    def _sync_tag_choices(self):
        """Offer the tags already in use as options in the editor's combo."""
        tags = [tag for tag, _ in notes_mod.list_tags() if tag]
        if tags == self._tag_choices:
            return
        self._tag_choices = tags
        self._suppress_meta_save = True
        # remove_all() clears the combo's entry too — put its text back.
        tag_entry = self.tag_combo.get_child()
        current = tag_entry.get_text()
        self.tag_combo.remove_all()
        self.tag_combo.append_text(_UNTAGGED_TEXT)
        for tag in tags:
            self.tag_combo.append_text(tag)
        tag_entry.set_text(current)
        self._suppress_meta_save = False

    def _restore_last_note(self):
        """Open the last note if it's still recent, otherwise show the list.

        The note only counts as "still open" for `remember_note_minutes` after
        the last interaction with it (0 disables the shortcut) — past that the
        panel opens on the list, as it does for a first-time show.
        """
        minutes = settings_mod.load_settings()["remember_note_minutes"]
        note = None
        if minutes:
            last_path = notes_mod.get_last_note_path(minutes * 60)
            if last_path:
                note = notes_mod.load_note(last_path)
        if note:
            self._load_note_in_editor(note)
        else:
            self._clear_editor()
            self._show_list_view()

    # --- view switching (list ⇄ editor) ---

    def _in_editor_view(self) -> bool:
        return self.main_stack.get_visible_child_name() == "editor"

    def _show_list_view(self):
        self.main_stack.set_visible_child_name("list")
        self.search_box.show()
        self._update_bottom_bar()
        self.bottom_bar.show()
        self.search.grab_focus()

    def _show_editor_view(self):
        self.main_stack.set_visible_child_name("editor")
        self.search_box.hide()
        # The preview renders the title as an H1 of its own, so the meta row
        # would only repeat it there.
        self.meta_row.set_visible(not self._preview_mode)
        self._update_bottom_bar()
        self.bottom_bar.show()
        self.text_view.grab_focus()

    def _update_bottom_bar(self):
        """Fill the bottom bar with the current destination's controls.

        Settings and the separator to its left are deliberately absent here:
        they hold the far-right slot in every view.
        """
        editing = self._in_editor_view()
        list_mode = not editing and not self._trash_mode
        self.btn_back.set_visible(not list_mode)
        self.btn_new.set_visible(list_mode)
        self.btn_open_trash.set_visible(list_mode)
        self.btn_empty_trash.set_visible(self._trash_mode and not editing)
        for btn in (self.btn_copy, self.btn_select_all, self.btn_find, self.btn_preview):
            btn.set_visible(editing)

    def _on_back(self, btn):
        # One back button for every nested destination — the editor first (the
        # trash list is what's behind a trashed note), then the trash itself.
        if self._in_editor_view():
            self._on_editor_back()
        else:
            self._on_close_trash(btn)

    def _on_editor_back(self, *_args):
        if self._preview_mode:
            self._on_toggle_preview(None)
        self._flush_save()
        self._clear_editor()
        if self._trash_mode:
            self._refresh_trash()
        else:
            self._refresh_notes(self.search.get_text())
        self._show_list_view()

    def _refresh_trash(self):
        for row in self.list_box.get_children():
            self.list_box.remove(row)

        trash_notes = notes_mod.list_trash()
        for note in trash_notes:
            self.list_box.add(TrashRow(note, self._restore_note, self._delete_permanently))

        self._set_status_count(len(trash_notes), prefix="Trash · ")

    def _set_status_count(self, count: int, prefix: str = ""):
        if count:
            self.status_label.set_text(f"{prefix}{count} note{'s' if count != 1 else ''}")
            self.status_label.show()
        else:
            self.status_label.set_text("")
            self.status_label.hide()

    def _clear_editor(self):
        self._close_find_bar()
        # A pending save would otherwise fire against the emptied buffer and
        # write it back over the note (or create a blank one).
        self._cancel_pending_save()
        buf = self.text_view.get_buffer()
        buf.handler_block_by_func(self._on_content_changed)
        buf.set_text("")
        buf.handler_unblock_by_func(self._on_content_changed)
        # Emptying the buffer isn't an edit to undo — and undoing across it
        # would put the closed note's body back under whatever opens next.
        self.undo_stack.reset()
        self._set_meta("", "")
        self._current_path = None
        self._default_title = None
        notes_mod.set_last_note_path(None)

    def _load_note_in_editor(self, note: dict):
        self._close_find_bar()
        self._current_path = note["path"]
        self._default_title = None
        if not self._trash_mode:
            notes_mod.set_last_note_path(self._current_path)
        buf = self.text_view.get_buffer()
        buf.handler_block_by_func(self._on_content_changed)
        # Only the body: the first line is the header, and it belongs to the
        # meta row above the buffer.
        buf.set_text(note["body"])
        buf.handler_unblock_by_func(self._on_content_changed)
        self.undo_stack.reset()
        self._sync_tag_choices()
        self._set_meta(note["title"], note["tag"])
        if self._preview_mode:
            self.web_view.load_html(
                preview_mod.build_preview_html(self._preview_source(), self.get_style_context()),
                "file:///",
            )
        self._show_editor_view()

    def _set_meta(self, title: str, tag: str):
        """Fill the meta row without it reading as a user edit."""
        self._suppress_meta_save = True
        self.title_entry.set_text(title)
        self.tag_combo.get_child().set_text(tag or _UNTAGGED_TEXT)
        self._suppress_meta_save = False

    def _preview_source(self) -> str:
        """The note as standalone Markdown, title included.

        The buffer holds only the body now, so the H1 has to be put back or
        the rendered document would start mid-content.
        """
        buf = self.text_view.get_buffer()
        body = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)
        title = self.title_entry.get_text().strip()
        return f"# {title}\n\n{body}" if title else body

    def _schedule_save(self):
        self._cancel_pending_save()
        self._save_timeout = GLib.timeout_add(800, self._do_save)

    def _cancel_pending_save(self):
        if self._save_timeout is not None:
            GLib.source_remove(self._save_timeout)
            self._save_timeout = None

    def _flush_save(self):
        """Commit everything outstanding — before leaving the note behind.

        Not only the debounced body: the title and tag commit on focus-out,
        which never arrives when the note is left by Escape while one of them
        still holds the focus.
        """
        self._cancel_pending_save()
        if self._in_editor_view():
            self._do_save()

    def _do_save(self):
        self._save_timeout = None
        if self._trash_mode:
            return False
        buf = self.text_view.get_buffer()
        body = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)
        title = self.title_entry.get_text().strip()
        tag = self.tag_combo.get_child().get_text()
        if notes_mod.normalize_tag(tag) == _UNTAGGED_TEXT:
            tag = ""
        if not title:
            # Don't let a note end up called "Untitled" when its body already
            # says what it is. Writing the derived title back into the entry
            # keeps the list and the meta row agreeing; typing over it stops
            # the derivation, since the entry is no longer empty.
            title = self._derive_title(body)
            if title:
                self._set_meta(title, tag)
        if not body.strip() and (not title or title == self._default_title):
            # Nothing but the default title — an abandoned "new note" still
            # leaves no file behind.
            return False
        self._default_title = None
        self._current_path = notes_mod.save_note(self._current_path, title, tag, body)
        notes_mod.set_last_note_path(self._current_path)
        self._refresh_notes(self.search.get_text())
        return False

    def _derive_title(self, body: str) -> str:
        for line in body.splitlines():
            line = line.strip().lstrip("#").strip()
            if line:
                return line[:60]
        return ""

    def _save_meta(self):
        """Commit the title/tag at a transition point — focus-out, Enter, or
        a pick from the dropdown.

        Deliberately not debounced like the body: the title drives the note's
        filename through save_note(), so saving mid-word would rename the file
        once per keystroke.
        """
        if self._suppress_meta_save or self._trash_mode:
            return
        self._cancel_pending_save()
        self._do_save()

    def _on_meta_focus_out(self, widget, event):
        # GTK keeps painting an entry's selection once it loses focus, so the
        # select-all a new note opens with would stay highlighted while the
        # caret is already down in the body. Collapse it to the caret.
        pos = widget.get_position()
        widget.select_region(pos, pos)
        self._save_meta()
        return False

    def _on_title_activate(self, entry):
        self._save_meta()
        self.text_view.grab_focus()

    def _on_tag_activate(self, entry):
        self._save_meta()
        self.text_view.grab_focus()

    def _on_tag_combo_changed(self, combo):
        # Only fires for picks from the list; typing in the combo's entry
        # goes to that entry's own signals, and waits for focus-out/Enter.
        if combo.get_active() != -1:
            self._save_meta()

    def _on_open_settings(self, btn):
        dialog = SettingsDialog(self._apply_settings, self._reset_geometry)
        dialog.show_all()
        dialog.present()

    def _apply_settings(self, new_settings, changed_key=None):
        if changed_key in ("corner", "width_percent", "height_percent"):
            settings_mod.clear_remembered_geometry()
        x, y, w, h = geometry_mod.get_target_geometry()
        geometry_mod.apply_geometry(self, x, y, w, h)

    def _on_search(self, entry):
        if not self._trash_mode:
            self._refresh_notes(entry.get_text())

    def _on_row_activated(self, listbox, row):
        if hasattr(row, "note"):
            self._load_note_in_editor(row.note)

    def _on_new_note(self, btn):
        self._close_find_bar()
        self._cancel_pending_save()
        self._current_path = None
        notes_mod.set_last_note_path(None)
        buf = self.text_view.get_buffer()
        buf.handler_block_by_func(self._on_content_changed)
        buf.set_text("")
        buf.handler_unblock_by_func(self._on_content_changed)
        self.undo_stack.reset()
        self._sync_tag_choices()
        # A note started while the list is filtered by a tag inherits it —
        # that filter is the category the user is currently working in.
        self._default_title = _default_note_title()
        self._set_meta(self._default_title, self._tag_filter or "")
        self._show_editor_view()
        self.title_entry.grab_focus()

    # --- trash ---

    def _on_open_trash(self, btn):
        if self._preview_mode:
            self._on_toggle_preview(None)
        self._trash_mode = True
        self.text_view.set_editable(False)
        self._clear_editor()
        self._set_meta_sensitive(False)
        self.search.set_sensitive(False)
        self.tag_filter.set_sensitive(False)
        self._refresh_trash()
        self._show_list_view()

    def _on_close_trash(self, btn):
        self._trash_mode = False
        self.text_view.set_editable(True)
        self._clear_editor()
        self._set_meta_sensitive(True)
        self.search.set_sensitive(True)
        self.tag_filter.set_sensitive(True)
        self._refresh_notes(self.search.get_text())
        self._show_list_view()

    def _set_meta_sensitive(self, sensitive: bool):
        """A trashed note opens read-only — that has to cover its header too,
        which lives outside the (already non-editable) text view."""
        self.title_entry.set_sensitive(sensitive)
        self.tag_combo.set_sensitive(sensitive)

    def _restore_note(self, path: Path):
        notes_mod.restore_note(path)
        if self._current_path == path:
            self._clear_editor()
        self._refresh_trash()

    def _delete_permanently(self, path: Path):
        if path.exists():
            path.unlink()
        if self._current_path == path:
            self._clear_editor()
        self._refresh_trash()

    def _on_empty_trash(self, btn):
        notes_mod.empty_trash()
        self._clear_editor()
        self._refresh_trash()

    # --- preview ---

    def _on_toggle_preview(self, btn):
        self._preview_mode = not self._preview_mode
        self._close_find_bar()
        self.btn_find.set_sensitive(not self._preview_mode)
        self.meta_row.set_visible(not self._preview_mode)
        if self._preview_mode:
            self.web_view.load_html(
                preview_mod.build_preview_html(self._preview_source(), self.get_style_context()),
                "file:///",
            )
            self.editor_stack.set_visible_child_name("preview")
            self.btn_preview.set_image(
                Gtk.Image.new_from_icon_name("document-edit-symbolic", Gtk.IconSize.SMALL_TOOLBAR)
            )
            self.btn_preview.set_tooltip_text("Edit")
        else:
            self.editor_stack.set_visible_child_name("editor")
            self.btn_preview.set_image(
                Gtk.Image.new_from_icon_name("view-reveal-symbolic", Gtk.IconSize.SMALL_TOOLBAR)
            )
            self.btn_preview.set_tooltip_text("Preview")

    # --- find in note ---

    def _on_toggle_find(self, btn):
        if self.find_revealer.get_reveal_child():
            self._close_find_bar()
        else:
            self.find_revealer.set_reveal_child(True)
            self.find_entry.grab_focus()

    def _close_find_bar(self):
        self.find_revealer.set_reveal_child(False)
        self._clear_find_highlights()
        self.find_entry.set_text("")
        self.find_count_label.set_text("")

    def _clear_find_highlights(self):
        buf = self.text_view.get_buffer()
        buf.remove_tag(self.find_tag, buf.get_start_iter(), buf.get_end_iter())
        buf.remove_tag(self.find_tag_current, buf.get_start_iter(), buf.get_end_iter())
        self._find_matches = []
        self._find_index = -1

    def _on_find_changed(self, entry):
        self._run_find(entry.get_text())

    def _run_find(self, query: str):
        buf = self.text_view.get_buffer()
        self._clear_find_highlights()
        if not query:
            self.find_count_label.set_text("")
            return
        start = buf.get_start_iter()
        while True:
            match = start.forward_search(query, Gtk.TextSearchFlags.CASE_INSENSITIVE, None)
            if not match:
                break
            match_start, match_end = match
            buf.apply_tag(self.find_tag, match_start, match_end)
            self._find_matches.append((match_start.get_offset(), match_end.get_offset()))
            start = match_end
        if self._find_matches:
            self._goto_find_match(0)
        else:
            self.find_count_label.set_text("0/0")

    def _goto_find_match(self, index: int):
        if not self._find_matches:
            return
        buf = self.text_view.get_buffer()
        if self._find_index != -1:
            s, e = self._find_matches[self._find_index]
            buf.remove_tag(self.find_tag_current, buf.get_iter_at_offset(s), buf.get_iter_at_offset(e))
        self._find_index = index % len(self._find_matches)
        s, e = self._find_matches[self._find_index]
        start_iter = buf.get_iter_at_offset(s)
        end_iter = buf.get_iter_at_offset(e)
        buf.apply_tag(self.find_tag_current, start_iter, end_iter)
        buf.place_cursor(start_iter)
        self.text_view.scroll_to_iter(start_iter, 0.1, False, 0, 0)
        self.find_count_label.set_text(f"{self._find_index + 1}/{len(self._find_matches)}")

    def _on_find_next(self, *_args):
        if self._find_matches:
            self._goto_find_match(self._find_index + 1)

    def _on_find_prev(self, *_args):
        if self._find_matches:
            self._goto_find_match(self._find_index - 1)

    def _on_find_key_press(self, entry, event):
        if event.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            mods = event.state & Gtk.accelerator_get_default_mod_mask()
            if mods == Gdk.ModifierType.SHIFT_MASK:
                self._on_find_prev()
                return True
        return False

    def _on_copy(self, btn):
        buf = self.text_view.get_buffer()
        if buf.get_has_selection():
            buf.copy_clipboard(Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD))
        else:
            text = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)
            Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(text, -1)

    def _on_select_all(self, btn):
        buf = self.text_view.get_buffer()
        buf.select_range(buf.get_start_iter(), buf.get_end_iter())
        self.text_view.grab_focus()

    def _undo_target(self) -> bool:
        """Whether Ctrl+Z belongs to the body right now.

        The history covers the buffer only: the title and tag entries are
        plain GTK 3 widgets with no undo of their own, and the find entry
        isn't the note. Unless the text view itself has the focus the
        shortcut has to pass through untouched. That also covers preview
        mode and a trashed note, where the view is hidden or read-only.
        """
        return self.text_view.has_focus() and self.text_view.get_editable()

    def _on_undo(self):
        self.undo_stack.undo()
        self.text_view.scroll_mark_onscreen(self.text_view.get_buffer().get_insert())
        return True

    def _on_redo(self):
        self.undo_stack.redo()
        self.text_view.scroll_mark_onscreen(self.text_view.get_buffer().get_insert())
        return True

    def _on_content_changed(self, buf):
        self._schedule_save()
        if self.find_revealer.get_reveal_child() and self.find_entry.get_text():
            self._run_find(self.find_entry.get_text())

    def _delete_note_by_path(self, path):
        notes_mod.delete_note(path)
        if self._current_path == path:
            self._clear_editor()
        self._refresh_notes(self.search.get_text())

    def _on_key_press(self, widget, event):
        if event.keyval == Gdk.KEY_Escape:
            if self.find_revealer.get_reveal_child():
                self._close_find_bar()
                return True
            # Escape is the back button: it unwinds one nested destination at
            # a time — find bar → note → trash → notes list — and only hides
            # the panel once there's nothing left to back out of.
            if self._in_editor_view() or self._trash_mode:
                self._on_back(None)
                return True
            self._hide()
            return None
        # Ctrl+Z / Ctrl+Shift+Z (and Ctrl+Y, for the other habit). The window
        # sees keys before the focused widget, so the guard is what keeps the
        # shortcut from firing while the caret is somewhere else.
        mods = event.state & Gtk.accelerator_get_default_mod_mask()
        key = Gdk.keyval_to_lower(event.keyval)
        ctrl = Gdk.ModifierType.CONTROL_MASK
        if key == Gdk.KEY_z and mods == ctrl and self._undo_target():
            return self._on_undo()
        if key == Gdk.KEY_z and mods == ctrl | Gdk.ModifierType.SHIFT_MASK and self._undo_target():
            return self._on_redo()
        if key == Gdk.KEY_y and mods == ctrl and self._undo_target():
            return self._on_redo()

    def _on_delete_event(self, widget, event):
        self._hide()
        return True

    def _on_focus_out(self, widget, event):
        self._focus_lost_at = time.monotonic()
        if not settings_mod.load_settings()["hide_on_focus_out"]:
            return False
        if self._hide_timeout:
            GLib.source_remove(self._hide_timeout)
        self._hide_timeout = GLib.timeout_add(200, self._hide_after_focus_out)
        return False

    def _on_focus_in(self, widget, event):
        if self._hide_timeout:
            GLib.source_remove(self._hide_timeout)
            self._hide_timeout = None
        return False

    def _hide_after_focus_out(self):
        self._hide_timeout = None
        self._hide()
        return False

    def _hide(self):
        # Dismissing the panel is a transition point: commit the debounced save
        # now, or the next show would reload the note from a stale file.
        self._flush_save()
        self._save_geometry()
        self._hidden_at = time.monotonic()
        if self._trash_mode:
            self._on_close_trash(None)
        elif self._in_editor_view() and self._current_path:
            # Re-stamp the pointer: the note stays "current" for the configured
            # window counted from here — dismissing the panel is the last
            # interaction with it, not the last keystroke.
            notes_mod.set_last_note_path(self._current_path)
        self.hide()

    def _request_focus(self):
        gdk_win = self.get_window()
        if gdk_win:
            try:
                ts = GdkX11.x11_get_server_time(gdk_win)
            except Exception:
                ts = Gdk.CURRENT_TIME
            gdk_win.focus(ts)
        if self._in_editor_view():
            self.text_view.grab_focus()
        else:
            self.search.grab_focus()

    def toggle(self):
        if self.get_visible():
            # Without keep-above the panel stays visible but buried behind
            # whatever window took the focus, which reads as "hidden" — in that
            # case the toggle must raise it, not hide it. The focus-out caused
            # by the tray click itself lands a few ms before this call, so a
            # very recent focus loss still counts as "was on top".
            if not self.has_toplevel_focus() and time.monotonic() - self._focus_lost_at > 0.3:
                self.present()
                GLib.idle_add(self._request_focus)
                return
            self._hide()
        else:
            if time.monotonic() - self._hidden_at < 0.3:
                return
            x, y, w, h = geometry_mod.get_target_geometry()
            self.resize(w, h)
            self.move(x, y)
            self._pending_position = True
            self._refresh_notes(self.search.get_text())
            self._restore_last_note()
            self.show_all()
            self.present()
            GLib.idle_add(self._request_focus)
