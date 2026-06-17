import re
from datetime import datetime
from pathlib import Path

NOTES_DIR = Path.home() / ".local" / "share" / "notepanel"
TRASH_DIR = NOTES_DIR / ".trash"


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
    q = query.lower()
    return [n for n in list_notes() if q in n["title"].lower() or q in n["content"].lower()]


def save_note(path: Path | None, title: str, content: str) -> Path:
    ensure_dir()
    if path is None:
        filename = f"{slug(title)}-{int(datetime.now().timestamp())}.md"
        path = NOTES_DIR / filename
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
