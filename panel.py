import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkX11", "3.0")
gi.require_version("WebKit2", "4.1")
from gi.repository import Gtk, Gdk, GdkX11, GLib, WebKit2
from pathlib import Path
import time
import markdown as md_lib
import notes as notes_mod

PANEL_WIDTH_RATIO = 0.20


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

        # search bar centrada
        search_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        search_box.set_name("toolbar")
        self.search = Gtk.SearchEntry()
        self.search.set_name("search-entry")
        self.search.set_placeholder_text("Search notes...")
        self.search.set_halign(Gtk.Align.FILL)
        self.search.connect("search-changed", self._on_search)
        search_box.set_center_widget(self.search)

        self.status_label = Gtk.Label(label="", xalign=0)
        self.status_label.set_name("status-label")

        # lista de notas
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_vexpand(True)

        self.list_box = Gtk.ListBox()
        self.list_box.set_name("note-list")
        self.list_box.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.list_box.connect("row-activated", self._on_row_activated)
        scroll.add(self.list_box)

        # editor
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

        self._preview_mode = False
        self.btn_preview = Gtk.Button.new_from_icon_name("view-reveal-symbolic", Gtk.IconSize.SMALL_TOOLBAR)
        self.btn_preview.set_name("btn-action")
        self.btn_preview.set_tooltip_text("Preview")
        self.btn_preview.connect("clicked", self._on_toggle_preview)

        editor_actions.pack_start(btn_copy, False, False, 0)
        editor_actions.pack_start(btn_select_all, False, False, 0)
        editor_actions.pack_end(self.btn_preview, False, False, 0)

        # stack: editor ↔ preview
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
        self.text_view.get_buffer().connect("changed", self._on_content_changed)
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
        editor_box.pack_start(self.editor_stack, True, True, 0)

        # botón nueva nota centrado abajo
        bottom_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        bottom_bar.set_name("bottom-bar")
        btn_new = Gtk.Button(label="+ New note")
        btn_new.set_name("btn-new")
        btn_new.connect("clicked", self._on_new_note)
        bottom_bar.set_center_widget(btn_new)

        root.pack_start(search_box, False, False, 0)
        root.pack_start(self.status_label, False, False, 0)
        root.pack_start(scroll, True, True, 0)
        root.pack_start(editor_box, True, True, 0)
        root.pack_start(bottom_bar, False, False, 0)

        self.add(root)

    def _get_target_geometry(self):
        display = Gdk.Display.get_default()
        monitor = display.get_primary_monitor() or display.get_monitor(0)
        geo = monitor.get_geometry()
        work = monitor.get_workarea()
        w = int(geo.width * PANEL_WIDTH_RATIO)
        h = work.height if work.height > 0 else geo.height
        y = work.y if work.height > 0 else geo.y
        x = geo.x + geo.width - w
        return x, y, w, h

    def _apply_geometry(self, x, y, w, h):
        self.set_size_request(w, h)
        gdk_win = self.get_window()
        if gdk_win:
            gdk_win.move_resize(x, y, w, h)
        else:
            self.resize(w, h)
            self.move(x, y)

    def _position_panel(self):
        x, y, w, h = self._get_target_geometry()
        self.set_size_request(w, h)

    def _on_map_event(self, widget, event):
        if self._pending_position:
            self._pending_position = False
            x, y, w, h = self._get_target_geometry()
            self._apply_geometry(x, y, w, h)
            GLib.timeout_add(80, lambda: self._apply_geometry(x, y, w, h) or False)
        return False

    def _refresh_notes(self, query: str = ""):
        for row in self.list_box.get_children():
            self.list_box.remove(row)

        self._notes = notes_mod.search_notes(query) if query else notes_mod.list_notes()

        for note in self._notes:
            self.list_box.add(NoteRow(note, self._delete_note_by_path))

        count = len(self._notes)
        self.status_label.set_text(f"{count} note{'s' if count != 1 else ''}")

    def _load_note_in_editor(self, note: dict):
        self._current_path = note["path"]
        buf = self.text_view.get_buffer()
        buf.handler_block_by_func(self._on_content_changed)
        buf.set_text(note["content"])
        buf.handler_unblock_by_func(self._on_content_changed)
        if self._preview_mode:
            content = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)
            self.web_view.load_html(self._build_preview_html(content), "file:///")

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

    def _on_search(self, entry):
        self._refresh_notes(entry.get_text())

    def _on_row_activated(self, listbox, row):
        if isinstance(row, NoteRow):
            self._load_note_in_editor(row.note)

    def _on_new_note(self, btn):
        self._current_path = None
        buf = self.text_view.get_buffer()
        buf.handler_block_by_func(self._on_content_changed)
        buf.set_text("# New note\n\n")
        buf.handler_unblock_by_func(self._on_content_changed)
        self.text_view.grab_focus()

    def _theme_hex(self, name: str, fallback: str) -> str:
        found, c = self.get_style_context().lookup_color(name)
        if not found:
            return fallback
        return "#{:02x}{:02x}{:02x}".format(int(c.red * 255), int(c.green * 255), int(c.blue * 255))

    def _build_preview_html(self, content: str) -> str:
        bg      = self._theme_hex("theme_base_color",        "#272727")
        fg      = self._theme_hex("theme_text_color",        "#ffffff")
        accent  = self._theme_hex("theme_selected_bg_color", "#da3450")
        border  = self._theme_hex("borders",                 "#181818")
        code_bg = self._theme_hex("theme_bg_color",          "#2c2c2c")

        body = md_lib.markdown(
            content,
            extensions=["fenced_code", "tables", "nl2br", "sane_lists"],
        )

        return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
    background: {bg};
    color: {fg};
    font-family: Ubuntu, sans-serif;
    font-size: 13px;
    line-height: 1.6;
    padding: 14px;
    word-wrap: break-word;
}}
h1, h2, h3, h4 {{
    color: {accent};
    margin: 1em 0 .4em;
    line-height: 1.2;
}}
h1 {{ font-size: 1.5em; border-bottom: 1px solid {border}; padding-bottom: .3em; }}
h2 {{ font-size: 1.25em; }}
h3 {{ font-size: 1.05em; }}
p {{ margin: .5em 0; }}
a {{ color: {accent}; }}
code {{
    background: {code_bg};
    border: 1px solid {border};
    border-radius: 4px;
    padding: 1px 5px;
    font-family: monospace;
    font-size: 12px;
}}
pre {{
    background: {code_bg};
    border: 1px solid {border};
    border-radius: 6px;
    padding: 10px 12px;
    overflow-x: auto;
    margin: .6em 0;
}}
pre code {{
    background: transparent;
    border: none;
    padding: 0;
    font-size: 12px;
}}
blockquote {{
    border-left: 3px solid {accent};
    margin: .5em 0;
    padding: .2em .8em;
    opacity: .8;
}}
ul, ol {{ padding-left: 1.4em; margin: .4em 0; }}
li {{ margin: .15em 0; }}
table {{ border-collapse: collapse; width: 100%; margin: .6em 0; }}
th, td {{ border: 1px solid {border}; padding: 5px 10px; text-align: left; }}
th {{ background: {code_bg}; color: {accent}; }}
hr {{ border: none; border-top: 1px solid {border}; margin: 1em 0; }}
</style></head><body>{body}</body></html>"""

    def _on_toggle_preview(self, btn):
        self._preview_mode = not self._preview_mode
        if self._preview_mode:
            buf = self.text_view.get_buffer()
            content = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)
            self.web_view.load_html(self._build_preview_html(content), "file:///")
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

    def _delete_note_by_path(self, path):
        notes_mod.delete_note(path)
        if self._current_path == path:
            self._current_path = None
            buf = self.text_view.get_buffer()
            buf.handler_block_by_func(self._on_content_changed)
            buf.set_text("")
            buf.handler_unblock_by_func(self._on_content_changed)
        self._refresh_notes(self.search.get_text())

    def _on_key_press(self, widget, event):
        if event.keyval == Gdk.KEY_Escape:
            self._hide()

    def _on_focus_out(self, widget, event):
        # delay para dar tiempo a que menús emergentes devuelvan el foco
        if self._hide_timeout:
            GLib.source_remove(self._hide_timeout)
        self._hide_timeout = GLib.timeout_add(200, self._hide_after_focus_out)
        return False

    def _on_focus_in(self, widget, event):
        # el foco volvió (p.ej. menú contextual cerrado) — cancelar el hide pendiente
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
            x, y, w, h = self._get_target_geometry()
            self.set_size_request(w, h)
            self.move(x, y)
            self._pending_position = True
            self.show_all()
            GLib.idle_add(self._request_focus)
