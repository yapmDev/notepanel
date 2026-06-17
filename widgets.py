import gi
gi.require_version("Gtk", "3.0")
from gi.repository import Gtk


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
