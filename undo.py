import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk
import time

# How long a run of typing keeps growing the same undo step. A pause longer
# than this starts a new one, so undo unwinds by "thought" rather than by
# keystroke even when the text itself would coalesce.
_COALESCE_SECONDS = 1.5

# Nothing here is written to disk, so the only cost of a deep history is RAM
# for the strings — but an unbounded list on a process that lives for days is
# still a leak. The oldest steps fall off the bottom.
_MAX_STEPS = 200


class UndoStack:
    """Undo/redo history for a `Gtk.TextBuffer`.

    GTK 3 has none of its own: `enable-undo` on `Gtk.TextBuffer` arrived in
    GTK 4, and the GTK 3 alternative is GtkSourceView, a whole source-editing
    widget to import for one feature. So the history is recorded here, from
    the buffer's own `insert-text`/`delete-range` signals.

    Only the body buffer is covered — the title and tag live in entries
    outside it and commit at transition points, not as an edit stream.

    Programmatic buffer fills (loading a note, clearing the editor) must not
    land in the history, or the first Ctrl+Z after opening a note would put
    the previous note's text back — and the autosave, which listens to the
    same buffer, would write it to the file. `reset()` after any such fill is
    what keeps a note's history its own.
    """

    def __init__(self, buf: Gtk.TextBuffer):
        self._buf = buf
        # Each step is (kind, offset, text): the edit as it was *applied*, so
        # undo inverts it and redo replays it.
        self._undo: list[tuple[str, int, str]] = []
        self._redo: list[tuple[str, int, str]] = []
        # Set while we're the ones editing the buffer, so applying a step
        # doesn't get recorded as a new one.
        self._applying = False
        self._last_edit_at = 0.0
        buf.connect("insert-text", self._on_insert)
        buf.connect("delete-range", self._on_delete)

    # --- recording ---

    def _on_insert(self, buf, location, text, length):
        if self._applying:
            return
        offset = location.get_offset()
        if not self._merge_insert(offset, text):
            self._push(("insert", offset, text))
        self._last_edit_at = time.monotonic()
        self._redo.clear()

    def _on_delete(self, buf, start, end):
        if self._applying:
            return
        offset = start.get_offset()
        text = buf.get_text(start, end, True)
        if not self._merge_delete(offset, text):
            self._push(("delete", offset, text))
        self._last_edit_at = time.monotonic()
        self._redo.clear()

    def _push(self, step: tuple[str, int, str]):
        self._undo.append(step)
        if len(self._undo) > _MAX_STEPS:
            del self._undo[0]

    def _mergeable(self) -> bool:
        return bool(self._undo) and time.monotonic() - self._last_edit_at < _COALESCE_SECONDS

    def _merge_insert(self, offset: int, text: str) -> bool:
        """Grow the current step with `text`, or report that it starts a new one.

        Typing merges up to word granularity: a newline always closes the step
        (so undo never swallows a whole paragraph at once) and so does the
        boundary from whitespace back into a word, which is what makes one
        Ctrl+Z take back one word. A paste — anything longer than a keystroke
        — is always its own step.
        """
        if not self._mergeable() or len(text) != 1 or text == "\n":
            return False
        kind, prev_offset, prev_text = self._undo[-1]
        if kind != "insert" or offset != prev_offset + len(prev_text):
            return False
        if prev_text[-1].isspace() and not text.isspace():
            return False
        self._undo[-1] = (kind, prev_offset, prev_text + text)
        return True

    def _merge_delete(self, offset: int, text: str) -> bool:
        """Same idea in reverse, for a held Backspace or Delete.

        The two directions grow the step from opposite ends: Backspace walks
        the offset back and prepends, Delete keeps the offset and appends.
        """
        if not self._mergeable() or len(text) != 1 or text == "\n":
            return False
        kind, prev_offset, prev_text = self._undo[-1]
        if kind != "delete":
            return False
        if offset + 1 == prev_offset:  # backspace
            if prev_text[0].isspace() and not text.isspace():
                return False
            self._undo[-1] = (kind, offset, text + prev_text)
            return True
        if offset == prev_offset:  # delete key
            if prev_text[-1].isspace() and not text.isspace():
                return False
            self._undo[-1] = (kind, prev_offset, prev_text + text)
            return True
        return False

    # --- applying ---

    def can_undo(self) -> bool:
        return bool(self._undo)

    def can_redo(self) -> bool:
        return bool(self._redo)

    def undo(self) -> bool:
        if not self._undo:
            return False
        step = self._undo.pop()
        kind, offset, text = step
        self._apply("delete" if kind == "insert" else "insert", offset, text)
        self._redo.append(step)
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        step = self._redo.pop()
        self._apply(*step)
        self._undo.append(step)
        return True

    def _apply(self, kind: str, offset: int, text: str):
        self._applying = True
        try:
            if kind == "insert":
                self._buf.insert(self._buf.get_iter_at_offset(offset), text)
                cursor = offset + len(text)
            else:
                start = self._buf.get_iter_at_offset(offset)
                end = self._buf.get_iter_at_offset(offset + len(text))
                self._buf.delete(start, end)
                cursor = offset
            self._buf.place_cursor(self._buf.get_iter_at_offset(cursor))
        finally:
            self._applying = False
        # The next keystroke starts a fresh step: merging it into whatever the
        # step before the undo was would make the two impossible to separate.
        self._last_edit_at = 0.0

    def reset(self):
        """Drop the history — the buffer no longer holds what it recorded."""
        self._undo.clear()
        self._redo.clear()
        self._last_edit_at = 0.0
