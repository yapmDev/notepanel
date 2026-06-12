import os
import re
from datetime import datetime
from pathlib import Path

NOTES_DIR = Path.home() / ".local" / "share" / "notepanel"


def ensure_dir():
    NOTES_DIR.mkdir(parents=True, exist_ok=True)


def slug(title: str) -> str:
    s = title.lower().strip()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"\s+", "-", s)
    return s or "note"


def list_notes() -> list[dict]:
    ensure_dir()
    notes = []
    for path in sorted(NOTES_DIR.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True):
        content = path.read_text(encoding="utf-8")
        lines = content.splitlines()
        title = lines[0].lstrip("# ").strip() if lines else path.stem
        preview = " ".join(lines[1:])[:80].strip() if len(lines) > 1 else ""
        notes.append({
            "path": path,
            "title": title,
            "preview": preview,
            "content": content,
            "mtime": path.stat().st_mtime,
        })
    return notes


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
    if path.exists():
        path.unlink()


def new_note_content(title: str = "New note") -> str:
    return f"# {title}\n\n"
