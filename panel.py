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
from widgets import NoteRow, TrashRow, SettingsDialog


class NotesPanel(Gtk.Window):
    def __init__(self):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.set_name("panel-root")
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_keep_above(True)
        self.set_type_hint(Gdk.WindowTypeHint.UTILITY)

        self._current_path: Path | None = None
        self._save_timeout: int | None = None
        self._notes: list[dict] = []
        self._pending_position = False
        self._hidden_at: float = 0.0
        self._hide_timeout: int | None = None
        self._trash_mode = False

        self._load_css()
        self._build_ui()
        self._refresh_notes()
        self._position_panel()

        self.connect("key-press-event", self._on_key_press)
        self.connect("map-event", self._on_map_event)
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

        search_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        search_box.set_name("toolbar")
        self.search = Gtk.SearchEntry()
        self.search.set_name("search-entry")
        self.search.set_placeholder_text("Search notes...")
        self.search.set_halign(Gtk.Align.FILL)
        self.search.connect("search-changed", self._on_search)
        search_box.set_center_widget(self.search)

        self.btn_settings = Gtk.Button.new_from_icon_name("emblem-system-symbolic", Gtk.IconSize.SMALL_TOOLBAR)
        self.btn_settings.set_name("btn-action")
        self.btn_settings.set_tooltip_text("Settings")
        self.btn_settings.connect("clicked", self._on_open_settings)
        search_box.pack_end(self.btn_settings, False, False, 0)

        self.status_label = Gtk.Label(label="", xalign=0)
        self.status_label.set_name("status-label")

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

        editor_actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        editor_actions.set_name("editor-actions")

        btn_copy = Gtk.Button.new_from_icon_name("edit-copy-symbolic", Gtk.IconSize.SMALL_TOOLBAR)
        btn_copy.set_name("btn-action")
        btn_copy.set_tooltip_text("Copy")
        btn_copy.connect("clicked", self._on_copy)

        btn_select_all = Gtk.Button.new_from_icon_name("edit-select-all-symbolic", Gtk.IconSize.SMALL_TOOLBAR)
        btn_select_all.set_name("btn-action")
        btn_select_all.set_tooltip_text("Select all")
        btn_select_all.connect("clicked", self._on_select_all)

        self.btn_find = Gtk.Button.new_from_icon_name("edit-find-symbolic", Gtk.IconSize.SMALL_TOOLBAR)
        self.btn_find.set_name("btn-action")
        self.btn_find.set_tooltip_text("Find in note")
        self.btn_find.connect("clicked", self._on_toggle_find)

        self._preview_mode = False
        self.btn_preview = Gtk.Button.new_from_icon_name("view-reveal-symbolic", Gtk.IconSize.SMALL_TOOLBAR)
        self.btn_preview.set_name("btn-action")
        self.btn_preview.set_tooltip_text("Preview")
        self.btn_preview.connect("clicked", self._on_toggle_preview)

        editor_actions.pack_start(btn_copy, False, False, 0)
        editor_actions.pack_start(btn_select_all, False, False, 0)
        editor_actions.pack_start(self.btn_find, False, False, 0)
        editor_actions.pack_end(self.btn_preview, False, False, 0)

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
        self.find_revealer.set_transition_type(Gtk.RevealerTransitionType.SLIDE_DOWN)
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

        editor_box.pack_start(editor_actions, False, False, 0)
        editor_box.pack_start(self.find_revealer, False, False, 0)
        editor_box.pack_start(self.editor_stack, True, True, 0)

        # bottom bar — shared container, widgets toggled per mode
        bottom_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        bottom_bar.set_name("bottom-bar")

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

        self.btn_back = Gtk.Button(label="← Back")
        self.btn_back.set_name("btn-back")
        self.btn_back.connect("clicked", self._on_close_trash)
        self.btn_back.set_no_show_all(True)

        self.btn_empty_trash = Gtk.Button(label="Empty trash")
        self.btn_empty_trash.set_name("btn-empty-trash")
        self.btn_empty_trash.connect("clicked", self._on_empty_trash)
        self.btn_empty_trash.set_no_show_all(True)

        bottom_bar.pack_start(self.btn_back, False, False, 0)
        bottom_bar.pack_start(self.btn_new, True, True, 0)
        bottom_bar.pack_end(self.btn_empty_trash, False, False, 0)
        bottom_bar.pack_end(self.btn_open_trash, False, False, 0)

        root.pack_start(search_box, False, False, 0)
        root.pack_start(self.status_label, False, False, 0)
        root.pack_start(scroll, True, True, 0)
        root.pack_start(editor_box, True, True, 0)
        root.pack_start(bottom_bar, False, False, 0)

        self.add(root)

    def _position_panel(self):
        x, y, w, h = geometry_mod.get_target_geometry()
        self.set_size_request(w, h)

    def _on_map_event(self, widget, event):
        if self._pending_position:
            self._pending_position = False
            x, y, w, h = geometry_mod.get_target_geometry()
            geometry_mod.apply_geometry(self, x, y, w, h)
            GLib.timeout_add(80, lambda: geometry_mod.apply_geometry(self, x, y, w, h) or False)
        return False

    def _refresh_notes(self, query: str = ""):
        for row in self.list_box.get_children():
            self.list_box.remove(row)

        self._notes = notes_mod.search_notes(query) if query else notes_mod.list_notes()

        for note in self._notes:
            self.list_box.add(NoteRow(note, self._delete_note_by_path))

        count = len(self._notes)
        self.status_label.set_text(f"{count} note{'s' if count != 1 else ''}")

    def _refresh_trash(self):
        for row in self.list_box.get_children():
            self.list_box.remove(row)

        trash_notes = notes_mod.list_trash()
        for note in trash_notes:
            self.list_box.add(TrashRow(note, self._restore_note, self._delete_permanently))

        count = len(trash_notes)
        self.status_label.set_text(f"Trash · {count} note{'s' if count != 1 else ''}")

    def _clear_editor(self):
        self._close_find_bar()
        buf = self.text_view.get_buffer()
        buf.handler_block_by_func(self._on_content_changed)
        buf.set_text("")
        buf.handler_unblock_by_func(self._on_content_changed)
        self._current_path = None

    def _load_note_in_editor(self, note: dict):
        self._close_find_bar()
        self._current_path = note["path"]
        buf = self.text_view.get_buffer()
        buf.handler_block_by_func(self._on_content_changed)
        buf.set_text(note["content"])
        buf.handler_unblock_by_func(self._on_content_changed)
        if self._preview_mode:
            content = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)
            self.web_view.load_html(
                preview_mod.build_preview_html(content, self.get_style_context()), "file:///"
            )

    def _schedule_save(self):
        if self._save_timeout is not None:
            GLib.source_remove(self._save_timeout)
        self._save_timeout = GLib.timeout_add(800, self._do_save)

    def _do_save(self):
        self._save_timeout = None
        buf = self.text_view.get_buffer()
        content = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)
        lines = content.splitlines()
        title = lines[0].lstrip("# ").strip() if lines else "Untitled"
        self._current_path = notes_mod.save_note(self._current_path, title, content)
        self._refresh_notes(self.search.get_text())
        return False

    def _on_open_settings(self, btn):
        dialog = SettingsDialog(self._apply_settings)
        dialog.show_all()
        dialog.present()

    def _apply_settings(self, new_settings):
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
        self._current_path = None
        buf = self.text_view.get_buffer()
        buf.handler_block_by_func(self._on_content_changed)
        buf.set_text("# New note\n\n")
        buf.handler_unblock_by_func(self._on_content_changed)
        self.text_view.grab_focus()

    # --- trash ---

    def _on_open_trash(self, btn):
        if self._preview_mode:
            self._on_toggle_preview(None)
        self._trash_mode = True
        self.text_view.set_editable(False)
        self._clear_editor()
        self.btn_new.hide()
        self.btn_open_trash.hide()
        self.btn_back.show()
        self.btn_empty_trash.show()
        self.search.set_sensitive(False)
        self._refresh_trash()

    def _on_close_trash(self, btn):
        self._trash_mode = False
        self.text_view.set_editable(True)
        self._clear_editor()
        self.btn_back.hide()
        self.btn_empty_trash.hide()
        self.btn_new.show()
        self.btn_open_trash.show()
        self.search.set_sensitive(True)
        self._refresh_notes(self.search.get_text())

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
        if self._preview_mode:
            buf = self.text_view.get_buffer()
            content = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)
            self.web_view.load_html(
                preview_mod.build_preview_html(content, self.get_style_context()), "file:///"
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
            self._hide()

    def _on_focus_out(self, widget, event):
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
        self._hidden_at = time.monotonic()
        if self._trash_mode:
            self._on_close_trash(None)
        self.hide()

    def _request_focus(self):
        gdk_win = self.get_window()
        if gdk_win:
            try:
                ts = GdkX11.x11_get_server_time(gdk_win)
            except Exception:
                ts = Gdk.CURRENT_TIME
            gdk_win.focus(ts)
        self.search.grab_focus()

    def toggle(self):
        if self.get_visible():
            self._hide()
        else:
            if time.monotonic() - self._hidden_at < 0.3:
                return
            x, y, w, h = geometry_mod.get_target_geometry()
            self.set_size_request(w, h)
            self.move(x, y)
            self._pending_position = True
            self._refresh_notes(self.search.get_text())
            self.show_all()
            GLib.idle_add(self._request_focus)
