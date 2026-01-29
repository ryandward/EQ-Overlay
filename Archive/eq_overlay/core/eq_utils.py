"""
Core utilities for EQ interaction - focus detection, window finding, input sending.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional


def is_eq_focused() -> bool:
    """Check if EverQuest or our overlay windows have focus using xdotool."""
    try:
        result = subprocess.run(
            ["xdotool", "getactivewindow", "getwindowname"],
            capture_output=True,
            text=True,
            timeout=1,
        )
        if result.returncode == 0:
            window_name = result.stdout.strip().lower()
            allowed_names = [
                "everquest",
                "eqgame",
                "wine",
                "project 1999",
                "eqlite",
                "eq overlay",
                "eq spell timer",
                "eq chat",
                "eq timers",
                "eq overlay notifications",
            ]
            return any(name in window_name for name in allowed_names)
        return True  # Default to visible if we can't detect
    except Exception:
        return True


def find_eq_window() -> Optional[str]:
    """Find the EQ window ID."""
    search_terms = ["EverQuest", "eqgame", "Project 1999"]
    for term in search_terms:
        try:
            result = subprocess.run(
                ["xdotool", "search", "--name", term],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip().split("\n")[0]
        except Exception:
            pass
    return None


def send_to_eq(command: str) -> bool:
    """Send a command to EQ via clipboard paste.
    
    Args:
        command: The full command including / prefix (e.g., "/gu Hello")
    
    Returns:
        True if successful, False otherwise.
    """
    import time
    
    window_id = find_eq_window()
    if not window_id:
        print(f"DEBUG send_to_eq: No EQ window found")
        return False
    try:
        # Command starts with /, strip it and paste the rest
        if command.startswith("/"):
            to_paste = command[1:]  # Everything after /
        else:
            to_paste = command

        print(f"DEBUG send_to_eq: putting on clipboard: '{to_paste}'")

        # Copy to clipboard using stdin (safer for special chars)
        result = subprocess.run(
            ["wl-copy"],
            input=to_paste.encode("utf-8"),
            timeout=2,
            check=True
        )
        time.sleep(0.05)  # Small delay to ensure clipboard is ready

        # Send / to open chat, paste, then Enter
        subprocess.run(["xdotool", "key", "--window", window_id, "slash"], timeout=1)
        time.sleep(0.02)
        subprocess.run(
            ["xdotool", "key", "--window", window_id, "shift+ctrl+v"], timeout=1
        )
        time.sleep(0.02)
        subprocess.run(["xdotool", "key", "--window", window_id, "Return"], timeout=2)

        return True
    except Exception as e:
        print(f"Error sending to EQ: {e}")
        return False


def play_notification_sound() -> None:
    """Play a notification sound for tells/alerts."""
    try:
        sound_files = [
            "/usr/share/sounds/freedesktop/stereo/message-new-instant.oga",
            "/usr/share/sounds/freedesktop/stereo/message.oga",
            "/usr/share/sounds/gnome/default/alerts/drip.ogg",
            "/usr/share/sounds/sound-icons/prompt.wav",
        ]

        for sound_file in sound_files:
            if Path(sound_file).exists():
                # Try paplay (PulseAudio), then aplay (ALSA)
                try:
                    subprocess.Popen(
                        ["paplay", sound_file],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    return
                except FileNotFoundError:
                    try:
                        subprocess.Popen(
                            ["aplay", "-q", sound_file],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                        )
                        return
                    except FileNotFoundError:
                        pass
    except Exception:
        pass  # Silent fail if no sound available


def decode_eq_text(text: str) -> str:
    """Decode EQ log file special entities."""
    return text.replace("&PCT;", "%").replace("&AMP;", "&")
