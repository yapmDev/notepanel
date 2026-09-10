import re
from datetime import datetime
from pathlib import Path

NOTES_DIR = Path.home() / ".local" / "share" / "notepanel"
TRASH_DIR = NOTES_DIR / ".trash"
_LAST_NOTE_PATH = NOTES_DIR / ".last-note"

_FILENAME_RE = re.compile(r"^(.*)-(\d+)\.md$")

# Separates the title from the tag on a note's first line. That line is
# metadata, never body: the editor shows only what follows it.
HEADER_SEP = "::"


def ensure_dir():
    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    TRASH_DIR.mkdir(parents=True, exist_ok=True)


def slug(title: str) -> str:
    s = title.lower().strip()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"\s+", "-", s)
    return s or "note"


def normalize_tag(tag: str) -> str:
    """One canonical spelling per tag, so the filter groups them as one."""
    return re.sub(r"\s+", " ", tag.strip().lower())


def parse_header(content: str) -> tuple[str, str, str]:
    """Split a note's raw text into `(title, tag, body)`.

    The first line holds `Title :: tag`; a note with no tag omits the
    separator entirely and its first line is just the title. Splitting on
    the *last* separator keeps a title containing `::` intact, since the tag
    is always the trailing token.
    """
    head, _, rest = content.partition("\n")
    title_part, sep, tag_part = head.rpartition(HEADER_SEP)
    tag = normalize_tag(tag_part) if sep else ""
    # A separator with nothing after it isn't one: keeping the whole line as
    # the title is what makes a title ending in `::` round-trip unchanged.
    title = title_part.strip() if tag else head.strip()
    # The blank line under the header is separation, not content — dropping
    # one keeps round-trips from accumulating blank lines at the top.
    if rest.startswith("\n"):
        rest = rest[1:]
    return title, tag, rest


def compose(title: str, tag: str, body: str) -> str:
    """Inverse of `parse_header` — the note exactly as it goes to disk."""
    title = title.strip() or "Untitled"
    tag = normalize_tag(tag)
    header = f"{title} {HEADER_SEP} {tag}" if tag else title
    body = body.lstrip("\n")
    return f"{header}\n\n{body}" if body else f"{header}\n"


def _note_from_path(path: Path) -> dict:
    content = path.read_text(encoding="utf-8")
    title, tag, body = parse_header(content)
    return {
        "path": path,
        "title": title or path.stem,
        "tag": tag,
        "body": body,
        # Long enough to fill the list row's two preview lines; the label
        # ellipsizes whatever is left over.
        "preview": " ".join(body.split())[:200],
        "content": content,
        "mtime": path.stat().st_mtime,
    }


def _filter_by_tag(notes: list[dict], tag: str | None) -> list[dict]:
    """`None` keeps every note; `""` keeps only the untagged ones."""
    if tag is None:
        return notes
    return [n for n in notes if n["tag"] == tag]


def load_note(path: Path) -> dict | None:
    if not path.exists():
        return None
    return _note_from_path(path)


def list_notes(tag: str | None = None) -> list[dict]:
    ensure_dir()
    notes = [
        _note_from_path(p)
        for p in sorted(NOTES_DIR.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    ]
    return _filter_by_tag(notes, tag)


def list_tags() -> list[tuple[str, int]]:
    """Every tag in use with its note count, untagged first (as `""`).

    Derived from the notes themselves rather than tracked separately, so a
    tag exists exactly as long as some note still carries it.
    """
    counts: dict[str, int] = {}
    for note in list_notes():
        counts[note["tag"]] = counts.get(note["tag"], 0) + 1
    return sorted(counts.items())


def list_trash() -> list[dict]:
    ensure_dir()
    return [
        _note_from_path(p)
        for p in sorted(TRASH_DIR.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    ]


def search_notes(query: str, tag: str | None = None) -> list[dict]:
    ensure_dir()
    q = query.lower().strip()
    if not q:
        return list_notes(tag)
    matched = []
    for p in sorted(NOTES_DIR.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True):
        match = _FILENAME_RE.match(p.name)
        name_part = match.group(1) if match else p.stem
        note = _note_from_path(p)
        # The filename is a slug of the title, so it misses punctuation and
        # accents the title itself still has — match both.
        if q in name_part.lower() or q in note["title"].lower():
            matched.append(note)
    return _filter_by_tag(matched, tag)


def _synced_path(path: Path, new_slug: str) -> Path:
    match = _FILENAME_RE.match(path.name)
    if match and match.group(1) != new_slug:
        candidate = path.with_name(f"{new_slug}-{match.group(2)}.md")
        if not candidate.exists():
            path.rename(candidate)
            return candidate
    return path


def save_note(path: Path | None, title: str, tag: str, body: str) -> Path:
    ensure_dir()
    title = title.strip() or "Untitled"
    content = compose(title, tag, body)
    new_slug = slug(title)
    if path is None:
        filename = f"{new_slug}-{int(datetime.now().timestamp())}.md"
        path = NOTES_DIR / filename
    else:
        path = _synced_path(path, new_slug)
        # Saving is idempotent: rewriting identical bytes would still bump the
        # mtime, and the list is ordered by it — merely opening a note and
        # dismissing the panel would jump it to the top.
        if path.exists() and path.read_text(encoding="utf-8") == content:
            return path
    path.write_text(content, encoding="utf-8")
    return path


def delete_note(path: Path):
    if not path.exists():
        return
    ensure_dir()
    dest = TRASH_DIR / path.name
    if dest.exists():
        dest = TRASH_DIR / f"{path.stem}-{int(datetime.now().timestamp())}{path.suffix}"
    path.rename(dest)


def restore_note(path: Path) -> Path:
    ensure_dir()
    dest = NOTES_DIR / path.name
    if dest.exists():
        dest = NOTES_DIR / f"{path.stem}-{int(datetime.now().timestamp())}{path.suffix}"
    path.rename(dest)
    return dest


def empty_trash():
    ensure_dir()
    for path in TRASH_DIR.glob("*.md"):
        path.unlink()


def get_last_note_path(max_age_seconds: float | None = None) -> Path | None:
    """Path of the note last open in the editor, or None.

    The pointer file holds `{unix_timestamp}\\n{path}` — the timestamp is
    refreshed on every interaction with the note, so its age measures how
    long the note has been untouched. A pointer older than
    `max_age_seconds`, or one lacking a timestamp (written by an older
    version), counts as absent.
    """
    try:
        raw = _LAST_NOTE_PATH.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not raw:
        return None

    stamp, _, raw_path = raw.partition("\n")
    if not raw_path:
        return None
    if max_age_seconds is not None:
        try:
            age = datetime.now().timestamp() - float(stamp)
        except ValueError:
            return None
        if age > max_age_seconds:
            return None

    path = Path(raw_path.strip())
    return path if path.exists() else None


def set_last_note_path(path: Path | None):
    """Point at `path` (stamped now), or drop the pointer when None."""
    ensure_dir()
    if path is None:
        _LAST_NOTE_PATH.unlink(missing_ok=True)
    else:
        stamp = int(datetime.now().timestamp())
        _LAST_NOTE_PATH.write_text(f"{stamp}\n{path}", encoding="utf-8")
