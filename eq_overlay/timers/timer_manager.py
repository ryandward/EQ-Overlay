"""
Timer manager - manages active buff/debuff timers.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from ..core.data import ActiveTimer, TimerCategory, SpellInfo
from ..core.signals import Signals


class TimerManager:
    """
    Manages active spell timers.
    
    Handles:
    - Adding/removing timers
    - Expiration checking
    - Sorting by category and time
    """

    def __init__(self, signals: Signals):
        self._signals = signals
        self._timers: dict[tuple[str, str], ActiveTimer] = {}  # (spell_name, target) -> timer

    def add(self, timer: ActiveTimer) -> None:
        """Add or update a timer."""
        key = (timer.spell_name, timer.target)

        # If timer already exists, update end time (refresh)
        if key in self._timers:
            existing = self._timers[key]
            if timer.end_time > existing.end_time:
                self._timers[key] = timer
        else:
            self._timers[key] = timer

        self._signals.timer_updated.emit()

    def remove(self, spell_name: str, target: str = "You") -> Optional[ActiveTimer]:
        """Remove a timer by spell name and target."""
        key = (spell_name, target)
        timer = self._timers.pop(key, None)
        if timer:
            self._signals.timer_updated.emit()
        return timer

    def remove_all_for_target(self, target: str) -> None:
        """Remove all timers for a target (e.g., on death)."""
        to_remove = [k for k in self._timers if k[1] == target]
        for key in to_remove:
            del self._timers[key]
        if to_remove:
            self._signals.timer_updated.emit()

    def clear(self) -> None:
        """Clear all timers."""
        self._timers.clear()
        self._signals.timer_updated.emit()

    def get_all(self) -> list[ActiveTimer]:
        """Get all active timers, sorted."""
        timers = list(self._timers.values())
        timers.sort(key=lambda t: t.sort_key)
        return timers

    def get_by_category(self, category: TimerCategory) -> list[ActiveTimer]:
        """Get timers for a specific category."""
        return [t for t in self._timers.values() if t.category == category]

    def check_expired(self) -> list[ActiveTimer]:
        """Remove and return expired timers."""
        now = datetime.now()
        expired = []
        to_remove = []

        for key, timer in self._timers.items():
            if timer.is_expired:
                expired.append(timer)
                to_remove.append(key)

        for key in to_remove:
            del self._timers[key]

        if expired:
            self._signals.timer_updated.emit()

        return expired

    def pause_all(self, pause_time: datetime) -> None:
        """Record pause time for all timers (used for logout tracking)."""
        # Timers don't tick while logged out - would need to extend them
        pass

    def resume_all(self, resume_time: datetime, paused_at: datetime) -> None:
        """Extend timers by the paused duration."""
        pause_duration = resume_time - paused_at
        for timer in self._timers.values():
            timer.extend(pause_duration)
        self._signals.timer_updated.emit()

    def find_by_spell(self, spell_name: str) -> list[ActiveTimer]:
        """Find all timers for a spell name."""
        return [t for t in self._timers.values() if t.spell_name == spell_name]

    def has_timer(self, spell_name: str, target: str = "You") -> bool:
        """Check if a timer exists."""
        return (spell_name, target) in self._timers

    @property
    def count(self) -> int:
        return len(self._timers)
