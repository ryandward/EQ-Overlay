"""
Shared Qt signals for the application.
"""

from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal


class Signals(QObject):
    """Central signal hub for the application."""

    # Chat signals
    chat_message_received = pyqtSignal(object)  # ChatMessage
    conversation_updated = pyqtSignal(str)  # conversation_id

    # Timer signals
    timer_updated = pyqtSignal()
    timer_added = pyqtSignal(object)  # ActiveTimer
    timer_removed = pyqtSignal(str)  # spell_name

    # DPS signals
    dps_updated = pyqtSignal(object)  # DPSData dict

    # Casting signals
    cast_started = pyqtSignal(str, float)  # spell_name, cast_time_ms
    cast_completed = pyqtSignal(str)  # spell_name
    cast_interrupted = pyqtSignal()

    # Notification signals (for the shared notification center)
    notification_requested = pyqtSignal(object)  # Notification

    # Log/status signals
    log_message = pyqtSignal(str)
    status_changed = pyqtSignal(str)

    # Character/state signals
    character_changed = pyqtSignal(str)  # character_name
    zone_changed = pyqtSignal(str)  # zone_name
    game_state_changed = pyqtSignal(str)  # state name (active, paused, etc.)

    # Window signals
    eq_focus_changed = pyqtSignal(bool)  # is_focused
