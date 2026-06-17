# notepanel

A lightweight notes panel for Linux/GNOME. Notes are stored as plain Markdown files in `~/.local/share/notepanel/`.

## Features

- Tray icon — toggle panel or stop service
- Quick capture via hotkey (`SIGUSR1`) — opens a popup pre-filled with clipboard content
- Markdown editor with live preview
- Auto-save, full-text search
- Recycling bin
- Follows the system theme (GTK3)
- systemd user service friendly

## Requirements

- Linux / GNOME, X11 or XWayland
- Python 3.12+
- `gir1.2-webkit2-4.1` / `webkit2gtk4.1` / `webkit2gtk`

## Install

```bash
git clone https://github.com/yapmDev/notepanel.git
cd notepanel
python3 main.py
```

## License

MIT
