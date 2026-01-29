"""
EQ spell duration calculation formulas.
"""

from __future__ import annotations

import math


class DurationFormula:
    """Calculate spell durations based on EQ's formula system."""
    
    SECONDS_PER_TICK = 6
    PERMANENT_TICKS = 72000

    @staticmethod
    def calculate(formula: int, base: int, level: int) -> int:
        """Calculate duration in seconds."""
        ticks = DurationFormula._get_ticks(formula, base, level)
        return ticks * DurationFormula.SECONDS_PER_TICK

    @staticmethod
    def _get_ticks(formula: int, base: int, level: int) -> int:
        match formula:
            case 0:
                return 0
            case 1:
                ticks = math.ceil(level / 2.0)
                return min(ticks, base) if base > 0 else ticks
            case 2:
                ticks = math.ceil(level / 5.0 * 3)
                return min(ticks, base) if base > 0 else ticks
            case 3:
                ticks = level * 30
                return min(ticks, base) if base > 0 else ticks
            case 4:
                return base if base > 0 else 50
            case 5:
                return base if base > 0 else 3
            case 6:
                ticks = math.ceil(level / 2.0)
                return min(ticks, base) if base > 0 else ticks
            case 7:
                ticks = level
                return min(ticks, base) if base > 0 else ticks
            case 8:
                ticks = level + 10
                return min(ticks, base) if base > 0 else ticks
            case 9:
                ticks = (level * 2) + 10
                if base > 60:
                    return base
                return min(ticks, base) if base > 0 else ticks
            case 10:
                ticks = (level * 3) + 10
                if base > 60:
                    return base
                return min(ticks, base) if base > 0 else ticks
            case 11 | 12 | 15:
                return base
            case 50:
                return DurationFormula.PERMANENT_TICKS
            case 3600:
                return base if base > 0 else 3600
            case _:
                return base


def format_duration(seconds: float) -> str:
    """Format seconds as human-readable duration."""
    if seconds <= 0:
        return "0:00"
    total = int(seconds)
    if total >= 3600:
        h = total // 3600
        m = (total % 3600) // 60
        return f"{h}h{m:02d}m"
    else:
        m = total // 60
        s = total % 60
        return f"{m}:{s:02d}"


def relative_time(dt) -> str:
    """Convert datetime to relative string like '2m', '1h', 'yesterday'."""
    from datetime import datetime
    
    now = datetime.now()
    diff = now - dt

    if diff.total_seconds() < 60:
        return "now"
    elif diff.total_seconds() < 3600:
        return f"{int(diff.total_seconds() // 60)}m"
    elif diff.total_seconds() < 86400:
        return f"{int(diff.total_seconds() // 3600)}h"
    elif diff.days == 1:
        return "yesterday"
    elif diff.days < 7:
        return f"{diff.days}d"
    else:
        return dt.strftime("%m/%d")
