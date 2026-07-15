import re
from datetime import datetime
from pathlib import Path

NOTES_DIR = Path.home() / ".local" / "share" / "notepanel"
TRASH_DIR = NOTES_DIR / ".trash"

_FILENAME_RE = re.compile(r"^(.*)-(\d+)\.md$")


def ensure_dir():
    NOTES_DIR.mkdir(parents=True, exist_ok=True)
    TRASH_DIR.mkdir(parents=True, exist_ok=True)


def slug(title: str) -> str:
    s = title.lower().strip()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"\s+", "-", s)
    return s or "note"


def _note_from_path(path: Path) -> dict:
    content = path.read_text(encoding="utf-8")
    lines = content.splitlines()
    title = lines[0].lstrip("# ").strip() if lines else path.stem
    preview = " ".join(lines[1:])[:80].strip() if len(lines) > 1 else ""
    return {
        "path": path,
        "title": title,
        "preview": preview,
        "content": content,
        "mtime": path.stat().st_mtime,
    }


def list_notes() -> list[dict]:
    ensure_dir()
    return [
        _note_from_path(p)
        for p in sorted(NOTES_DIR.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    ]


def list_trash() -> list[dict]:
    ensure_dir()
    return [
        _note_from_path(p)
        for p in sorted(TRASH_DIR.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    ]


def search_notes(query: str) -> list[dict]:
    ensure_dir()
    q = query.lower().strip()
    if not q:
        return list_notes()
    matched_paths = []
    for p in NOTES_DIR.glob("*.md"):
        match = _FILENAME_RE.match(p.name)
        name_part = match.group(1) if match else p.stem
        if q in name_part.lower():
            matched_paths.append(p)
    matched_paths.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return [_note_from_path(p) for p in matched_paths]


def _synced_path(path: Path, new_slug: str) -> Path:
    match = _FILENAME_RE.match(path.name)
    if match and match.group(1) != new_slug:
        candidate = path.with_name(f"{new_slug}-{match.group(2)}.md")
        if not candidate.exists():
            path.rename(candidate)
            return candidate
    return path


def save_note(path: Path | None, title: str, content: str) -> Path:
    ensure_dir()
    new_slug = slug(title)
    if path is None:
        filename = f"{new_slug}-{int(datetime.now().timestamp())}.md"
        path = NOTES_DIR / filename
    else:
        path = _synced_path(path, new_slug)
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


def new_note_content(title: str = "New note") -> str:
    return f"# {title}\n\n"
