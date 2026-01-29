# EQ Overlay

A log-parsing overlay for Project 1999 that gives you a modern chat interface and spell timers without touching the game client.

![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)
![PyQt6](https://img.shields.io/badge/PyQt6-6.0+-green.svg)

## What it does

**Chat Panel** - Reads your EQ log and displays messages in a clean, iMessage-style interface. Conversations are threaded by channel (guild, group, ooc) and by person for tells. You can send tells directly from the overlay using xdotool. There's also a `/random` roll tracker that detects duplicate rolls and can pick winners.

**Timer Panel** - Tracks buff durations, debuffs, and shows a DPS meter during combat. Buffs you cast on others are grouped by spell name so you're not staring at 6 separate "Clarity" rows. Timers glow as they get close to expiring.

**Notifications** - Popup alerts for incoming tells and buff warnings. Shows up in the center of your screen, stays out of the way.

## Why

The EQ client is from 1999. The chat window is painful. Spell timers require you to either memorize durations or run a separate app. This sits on top of your game and handles both.

It parses the log file in real-time - no memory reading, no packet sniffing, no injection. Just reads text that EQ already writes to disk.

## Setup

### Requirements

- Python 3.10+
- PyQt6
- Linux (uses xdotool for sending tells)
- EQ logging enabled (`/log on` in game)

### Install

```bash
git clone https://github.com/yourusername/eq_overlay.git
cd eq_overlay
pip install -e .
```

### Configure

Copy the example config or create `~/.config/eq-overlay/config.json`:

```json
{
  "paths": {
    "log_dir": "~/EQLite/Logs",
    "spells_file": "~/EQLite/spells_us.txt",
    "whitelist_file": "~/.config/eq-overlay/p99_spells.txt",
    "data_dir": "~/.config/eq-overlay"
  },
  "server": "project1999",
  "character": {
    "default_level": 60
  },
  "windows": {
    "chat": {
      "side": "left",
      "width": 340,
      "sidebar_width": 100,
      "opacity": 0.92
    },
    "timers": {
      "side": "right",
      "width": 240,
      "opacity": 0.92
    }
  }
}
```

The `whitelist_file` filters spells to only P99-era stuff. Without it you'll see spells from later expansions that don't exist on the server.

### Run

```bash
python run.py
```

Or if installed:

```bash
eq-overlay
```

The overlay will ask you to select a character from your log files.

## Usage

### Chat

- Click a conversation in the sidebar to view it
- Type in the input box and press Enter to send a tell (requires the EQ window to be named correctly for xdotool)
- Right-click messages to copy
- The "Global" view shows all channels combined

### Timers

- Timers appear automatically when spells land
- Self-buffs, received buffs, and debuffs are color-coded
- Buffs you cast on others show in a separate section, grouped by spell
- DPS meter shows during combat, fades after 10 seconds of no damage

### Random Rolls

- Switch to the Random channel to see `/random` results
- Set a range and click "Pick Winner" to randomly select from valid rolls
- Duplicate rolls in the same range get flagged

### Settings

Right-click either panel → Settings to configure fonts, window sizes, etc.

## How spell tracking works

The overlay watches for patterns in your log:

1. `You begin casting Clarity.` → starts tracking a pending cast
2. `Soandso feels a rush of clarity.` → matches the "cast on other" message, creates timer

For bards (no "You begin casting" message), it learns item-to-spell associations. Use an item once on a character that gets the cast message, and it'll work on bards afterward.

Spell durations come from `spells_us.txt` with duration formulas calculated at your level.

## Viewport

To make room for the overlay without it covering your game, use the EQ `/viewport` command:

```
/viewport 340 0 1240 900
```

This shifts the game viewport right by 340px (the width of the chat panel). Adjust based on your setup.

## Known quirks

- Sending tells requires xdotool and a properly-named EQ window
- Some spells share "cast on you" messages, so the wrong spell might get picked occasionally
- Bard songs need the backtick/apostrophe normalization (Selo\`s vs Selo's) which is handled automatically

## License

MIT
