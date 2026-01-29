"""
Core functionality - data structures, signals, utilities.
"""

from .data import (
    ChannelType,
    TimerCategory,
    NotificationType,
    ChatMessage,
    Conversation,
    SpellInfo,
    ActiveTimer,
    PendingCast,
    TimePeriod,
    Notification,
    LogEntry,
    DPSData,
)
from .signals import Signals
from .duration import DurationFormula, format_duration, relative_time
from .eq_utils import is_eq_focused, find_eq_window, send_to_eq, play_notification_sound, decode_eq_text
from .log_parser import LogParser
from .log_watcher import LogWatcher, discover_characters, find_character_log

__all__ = [
    "ChannelType",
    "TimerCategory",
    "NotificationType",
    "ChatMessage",
    "Conversation",
    "SpellInfo",
    "ActiveTimer",
    "PendingCast",
    "TimePeriod",
    "Notification",
    "LogEntry",
    "DPSData",
    "Signals",
    "DurationFormula",
    "format_duration",
    "relative_time",
    "is_eq_focused",
    "find_eq_window",
    "send_to_eq",
    "play_notification_sound",
    "decode_eq_text",
    "LogParser",
    "LogWatcher",
    "discover_characters",
    "find_character_log",
]
