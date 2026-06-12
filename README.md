# ubuntu-notes

A lightweight notes panel for Ubuntu/GNOME. Click the tray icon (or use a hotkey) to slide in a full-height panel from the right edge of your primary monitor. Notes are stored as plain Markdown files.

## Features

- **Tray icon** — left-click to toggle, right-click to stop
- **Always on top**, anchored to the right edge of the primary monitor
- **Edit / Preview modes** — write in plain Markdown, switch to rendered view
- **Auto-save** — changes are saved automatically as you type
- **Search** — instant full-text search across all notes
- **Follows the system theme** — uses GTK3 / GNOME color variables
- **Hotkey support** via [keymit](https://github.com/yapmDev/keymit) (or any tool that can send `SIGUSR1`)
- **systemd user service** — starts automatically on login
- Notes stored as `.md` files in `~/.local/share/ubuntu-notes/`

## Requirements

- Ubuntu 22.04+ with GNOME
- Python 3.12+
- GTK3 (pre-installed on Ubuntu)

```bash
sudo apt install gir1.2-webkit2-4.1 python3-markdown
```

## Installation

```bash
git clone https://github.com/yapmDev/ubuntu_notes.git
cd ubuntu_notes
```

Run once to verify it works:

```bash
python3 main.py
```

## Run as a systemd user service (recommended)

Create `~/.config/systemd/user/ubuntu-notes.service`:

```ini
[Unit]
Description=ubuntu-notes panel
After=graphical-session.target

[Service]
ExecStart=/usr/bin/python3 /path/to/ubuntu_notes/main.py
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
```

Enable and start:

```bash
systemctl --user daemon-reload
systemctl --user enable --now ubuntu-notes
```

Useful commands:

```bash
systemctl --user status ubuntu-notes
systemctl --user restart ubuntu-notes
journalctl --user -u ubuntu-notes -f
```

## Hotkey integration

The app listens for `SIGUSR1` to toggle the panel. Bind it to any key using your preferred tool:

```bash
# toggle from the terminal
systemctl --user kill --signal=USR1 ubuntu-notes

# with keymit
keymit bind ctrl+n "systemctl --user kill --signal=USR1 ubuntu-notes"
```

## Usage

| Action | Result |
|--------|--------|
| Left-click tray icon | Toggle panel |
| Right-click tray icon | Menu (Stop service) |
| Click note in list | Load in editor |
| `✕` on a note | Delete note |
| `+ New note` button | Create new note |
| Preview button (👁) | Toggle Markdown preview |
| `Esc` | Close panel |
| Click outside panel | Close panel |
| `Ctrl+A` / `Ctrl+C` | Select all / Copy (standard) |

## Notes format

The first line of each file is used as the title:

```markdown
# My note title

Content goes here...
```

Files are named `<slug>-<timestamp>.md` and never renamed after creation, so external links remain stable.

## License

MIT
