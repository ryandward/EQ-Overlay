# EQ Overlay

A unified overlay for EverQuest Project 1999, providing:

- **Chat Panel** (left side) - iMessage-style chat with conversation sidebar
- **Timer Panel** (right side) - Buff timers and DPS meter  
- **Shared Notification Center** - Toast-style notifications for tells, buff warnings, etc.

## Installation

```bash
cd eq_overlay
pip install -e .
```

Or just run directly:

```bash
python run.py
```

## Configuration

Edit `config.json` to set your paths:

```json
{
  "paths": {
    "log_dir": "/path/to/EQLite/Logs",
    "spells_file": "/path/to/spells_us.txt",
    ...
  }
}
```

## Usage

```bash
# Auto-detect most recent character
eq-overlay

# Specify character
eq-overlay Sambal

# Chat only
eq-overlay --chat-only

# Timers only  
eq-overlay --timers-only

# Skip history loading
eq-overlay --no-history
```

## Requirements

- Python 3.10+
- PyQt6
- xdotool (for window focus detection and input sending)
- wl-copy (for Wayland clipboard, or xclip for X11)

## Project Structure

```
eq_overlay/
├── config.json              # Configuration file
├── eq_overlay/
│   ├── config.py            # Config loader
│   ├── main.py              # Entry point
│   ├── core/                # Shared core functionality
│   │   ├── data.py          # Data structures
│   │   ├── signals.py       # Qt signals
│   │   ├── log_parser.py    # Log parsing
│   │   ├── log_watcher.py   # Log file monitoring
│   │   ├── duration.py      # Spell duration formulas
│   │   └── eq_utils.py      # EQ interaction utilities
│   ├── ui/                  # Shared UI components
│   │   ├── theme.py         # Colors, fonts, styling
│   │   ├── base_window.py   # Base overlay window
│   │   └── notifications.py # Notification center
│   ├── chat/                # Chat module
│   │   ├── conversation_manager.py
│   │   ├── chat_panel.py
│   │   └── widgets.py
│   └── timers/              # Timer module
│       ├── spell_database.py
│       ├── timer_manager.py
│       ├── timer_panel.py
│       └── widgets.py
```
