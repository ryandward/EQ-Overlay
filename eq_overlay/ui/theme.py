"""
Unified theme for EQ Overlay - colors, fonts, and styling.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from PyQt6.QtGui import QColor, QFont


# =============================================================================
# COLOR UTILITIES
# =============================================================================


def get_luminance(color: QColor) -> float:
    """Calculate relative luminance of a color (0-1 scale)."""
    r = color.red() / 255.0
    g = color.green() / 255.0
    b = color.blue() / 255.0
    return 0.299 * r + 0.587 * g + 0.114 * b


def get_contrast_text_color(bg_color: QColor) -> QColor:
    """Return black or white text color based on background luminance."""
    if get_luminance(bg_color) > 0.45:
        return QColor(20, 20, 25)
    else:
        return QColor(250, 250, 255)


def get_contrast_shadow_color(bg_color: QColor) -> QColor:
    """Return appropriate shadow color based on background luminance."""
    if get_luminance(bg_color) > 0.45:
        return QColor(255, 255, 255, 60)
    else:
        return QColor(0, 0, 0, 120)


def rgb_to_hsl(r: int, g: int, b: int) -> tuple[float, float, float]:
    """Convert RGB (0-255) to HSL (h: 0-360, s: 0-1, l: 0-1)."""
    r, g, b = r / 255.0, g / 255.0, b / 255.0
    max_c = max(r, g, b)
    min_c = min(r, g, b)
    l = (max_c + min_c) / 2.0

    if max_c == min_c:
        h = s = 0.0
    else:
        d = max_c - min_c
        s = d / (2.0 - max_c - min_c) if l > 0.5 else d / (max_c + min_c)
        if max_c == r:
            h = (g - b) / d + (6.0 if g < b else 0.0)
        elif max_c == g:
            h = (b - r) / d + 2.0
        else:
            h = (r - g) / d + 4.0
        h *= 60.0

    return h, s, l


def hue_distance(h1: float, h2: float) -> float:
    """Calculate shortest distance between two hues (0-360)."""
    d = abs(h1 - h2)
    return min(d, 360 - d)


# =============================================================================
# CURATED PALETTE
# =============================================================================

# These colors are designed to:
# 1. Look good as bubble/bar backgrounds
# 2. Be clearly distinguishable from each other
# 3. Work well with the dark UI theme
# 4. Have appropriate contrast for text

CURATED_PALETTE: dict[str, tuple[QColor, int]] = {
    # name: (QColor for display, hue_center for matching)
    "green": (QColor(76, 140, 92), 135),      # Guild - forest green
    "gold": (QColor(180, 142, 58), 42),       # OOC - warm amber
    "purple": (QColor(128, 90, 160), 270),    # Group - soft purple
    "red": (QColor(175, 75, 75), 0),          # Shout - muted red
    "teal": (QColor(70, 145, 145), 180),      # Auction - teal
    "blue": (QColor(85, 120, 180), 220),      # Tell - slate blue
    "gray": (QColor(140, 140, 150), -1),      # Say - neutral
    "pink": (QColor(170, 100, 130), 330),     # Extra - dusty rose
    "cyan": (QColor(80, 160, 175), 190),      # Extra - cyan
    "orange": (QColor(190, 115, 65), 25),     # Extra - burnt orange
}


def snap_to_palette(color: QColor) -> QColor:
    """Snap an arbitrary color to the nearest curated palette color."""
    h, s, l = rgb_to_hsl(color.red(), color.green(), color.blue())

    # Low saturation colors -> gray
    if s < 0.15:
        return CURATED_PALETTE["gray"][0]

    # Find closest hue match
    best_match = "gray"
    best_distance = 360.0

    for name, (_, hue_center) in CURATED_PALETTE.items():
        if hue_center < 0:  # Skip gray, it's for low saturation
            continue
        dist = hue_distance(h, hue_center)
        if dist < best_distance:
            best_distance = dist
            best_match = name

    return CURATED_PALETTE[best_match][0]


# =============================================================================
# EQ COLOR LOADING
# =============================================================================

# EQ UserColor numbers to channel types (from EQ Options > Colors tab)
EQ_USERCOLOR_MAP: dict[int, str] = {
    1: "say",
    2: "tell",
    3: "group",
    4: "guild",
    5: "ooc",
    6: "auction",
    7: "shout",
    8: "emote",
}


def load_eq_colors(ini_path: Path) -> dict[int, QColor]:
    """Parse eqclient.ini and return User_X colors as QColor objects."""
    colors = {}
    if not ini_path.exists():
        return colors

    try:
        text = ini_path.read_text(errors="ignore")
        in_section = False
        color_data: dict[int, dict[str, int]] = {}

        for line in text.splitlines():
            line = line.strip()
            if line.startswith("["):
                in_section = line.lower() == "[textcolors]"
                continue
            if not in_section:
                continue
            if "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()

            # Parse User_X_Red/Green/Blue
            match = re.match(r"User_(\d+)_(Red|Green|Blue)", key)
            if match:
                user_num = int(match.group(1))
                component = match.group(2)
                if user_num not in color_data:
                    color_data[user_num] = {}
                try:
                    color_data[user_num][component] = int(value)
                except ValueError:
                    pass

        # Convert to QColor
        for user_num, components in color_data.items():
            if "Red" in components and "Green" in components and "Blue" in components:
                colors[user_num] = QColor(
                    components["Red"],
                    components["Green"],
                    components["Blue"],
                )
    except Exception as e:
        print(f"Error loading EQ colors: {e}")

    return colors


# =============================================================================
# THEME CLASS
# =============================================================================


class Theme:
    """Centralized theme with all colors and fonts."""

    # Backgrounds
    BG_DARK = QColor(20, 20, 28, 245)
    BG_PANEL = QColor(28, 28, 38, 250)
    BG_HOVER = QColor(45, 45, 60, 200)
    BG_SELECTED = QColor(55, 55, 75, 230)
    BG_INPUT = QColor(35, 35, 48, 240)
    BG_BAR = QColor(30, 30, 40, 220)

    # Default channel colors (from curated palette)
    CHANNEL_GUILD = CURATED_PALETTE["green"][0]
    CHANNEL_OOC = CURATED_PALETTE["gold"][0]
    CHANNEL_GROUP = CURATED_PALETTE["purple"][0]
    CHANNEL_SHOUT = CURATED_PALETTE["red"][0]
    CHANNEL_AUCTION = CURATED_PALETTE["teal"][0]
    CHANNEL_TELL = CURATED_PALETTE["blue"][0]
    CHANNEL_SAY = CURATED_PALETTE["gray"][0]

    # Timer categories
    TIMER_SELF_BUFF = QColor(0, 130, 180)      # Deep teal
    TIMER_RECEIVED_BUFF = QColor(40, 140, 60)  # Forest green
    TIMER_DEBUFF = QColor(180, 50, 50)         # Dark red
    TIMER_OTHER_BUFF = QColor(70, 100, 180)    # Steel blue

    # DPS colors
    DPS_YOU = QColor(200, 80, 80)              # Red for your damage
    DPS_OTHER = QColor(180, 120, 60)           # Orange for others

    # Text
    TEXT_PRIMARY = QColor(255, 255, 255)
    TEXT_SECONDARY = QColor(220, 220, 230)
    TEXT_DIM = QColor(120, 120, 140)
    TEXT_SHADOW = QColor(0, 0, 0, 180)

    # UI elements
    BORDER = QColor(60, 60, 80, 150)
    SEPARATOR = QColor(50, 50, 65, 200)
    UNREAD_BADGE = QColor(70, 130, 220)
    PAUSED = QColor(255, 200, 50)

    # Notification specific
    NOTIFICATION_BG = QColor(25, 25, 35, 240)
    NOTIFICATION_BORDER = QColor(60, 60, 80, 150)

    # Loaded from EQ ini - populated at startup
    _eq_colors: dict[str, QColor] = {}

    @classmethod
    def load_eq_colors(cls, ini_path: Path) -> None:
        """Load channel colors from eqclient.ini."""
        eq_colors = load_eq_colors(ini_path)
        print(f"Found {len(eq_colors)} user colors in ini")
        for user_num, qcolor in sorted(eq_colors.items()):
            if user_num in EQ_USERCOLOR_MAP:
                channel_name = EQ_USERCOLOR_MAP[user_num]
                cls._eq_colors[channel_name] = qcolor
                snapped = snap_to_palette(qcolor)
                print(
                    f"  User_{user_num} -> {channel_name}: "
                    f"RGB({qcolor.red()}, {qcolor.green()}, {qcolor.blue()}) -> "
                    f"RGB({snapped.red()}, {snapped.green()}, {snapped.blue()})"
                )

    @classmethod
    def get_channel_color(cls, channel: str) -> QColor:
        """Get color for a channel, snapped to curated palette."""
        channel_lower = channel.lower()

        # Check if loaded from ini - snap to palette
        if channel_lower in cls._eq_colors:
            return snap_to_palette(cls._eq_colors[channel_lower])

        # Fallback to hardcoded defaults
        fallback = {
            "guild": cls.CHANNEL_GUILD,
            "ooc": cls.CHANNEL_OOC,
            "group": cls.CHANNEL_GROUP,
            "shout": cls.CHANNEL_SHOUT,
            "auction": cls.CHANNEL_AUCTION,
            "tell": cls.CHANNEL_TELL,
            "say": cls.CHANNEL_SAY,
            "random": QColor(240, 240, 240),  # White for random (black text via contrast)
            "who": QColor(100, 180, 180),  # Teal for who listings
        }.get(channel_lower, cls.TEXT_PRIMARY)

        return snap_to_palette(fallback)

    # Font helpers
    @staticmethod
    def font(size: int = 11, bold: bool = False) -> QFont:
        weight = QFont.Weight.Bold if bold else QFont.Weight.Normal
        return QFont("Segoe UI", size, weight)

    @staticmethod
    def font_small(bold: bool = False) -> QFont:
        return Theme.font(9, bold)

    @staticmethod
    def font_medium(bold: bool = False) -> QFont:
        return Theme.font(11, bold)

    @staticmethod
    def font_large(bold: bool = False) -> QFont:
        return Theme.font(13, bold)
