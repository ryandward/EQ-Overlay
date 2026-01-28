"""
Shared data structures for EQ Overlay.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum, auto
from typing import Optional


# =============================================================================
# ENUMS
# =============================================================================


class ChannelType(Enum):
    """Chat channel types."""
    GUILD = "guild"
    OOC = "ooc"
    GROUP = "group"
    SHOUT = "shout"
    AUCTION = "auction"
    TELL = "tell"
    SAY = "say"
    RANDOM = "random"
    WHO = "who"


class TimerCategory(Enum):
    """Timer/buff categories."""
    SELF_BUFF = auto()
    RECEIVED_BUFF = auto()
    DEBUFF = auto()
    OTHER_BUFF = auto()


class NotificationType(Enum):
    """Types of notifications for the shared notification center."""
    CHAT_TELL = "chat_tell"
    CHAT_MESSAGE = "chat_message"
    BUFF_WARNING = "buff_warning"
    BUFF_FADED = "buff_faded"
    COMBAT_END = "combat_end"
    SYSTEM = "system"


# =============================================================================
# CHAT DATA STRUCTURES
# =============================================================================


@dataclass
class ChatMessage:
    """A single chat message."""
    timestamp: datetime
    channel: ChannelType
    sender: str
    content: str
    is_outgoing: bool = False
    tell_target: Optional[str] = None  # For tells, who is the other party

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "channel": self.channel.value,
            "sender": self.sender,
            "content": self.content,
            "is_outgoing": self.is_outgoing,
            "tell_target": self.tell_target,
        }

    @classmethod
    def from_dict(cls, d: dict) -> ChatMessage:
        return cls(
            timestamp=datetime.fromisoformat(d["timestamp"]),
            channel=ChannelType(d["channel"]),
            sender=d["sender"],
            content=d["content"],
            is_outgoing=d.get("is_outgoing", False),
            tell_target=d.get("tell_target"),
        )

    @property
    def display_time(self) -> str:
        """Format timestamp with date context."""
        now = datetime.now()
        today = now.date()
        msg_date = self.timestamp.date()
        time_str = self.timestamp.strftime("%H:%M")

        if msg_date == today:
            return time_str
        elif msg_date == today - timedelta(days=1):
            return f"Yesterday {time_str}"
        elif (today - msg_date).days < 7:
            return self.timestamp.strftime("%a %H:%M")
        else:
            return self.timestamp.strftime("%b %d %H:%M")

    @property
    def conversation_id(self) -> str:
        """Unique ID for the conversation this message belongs to."""
        if self.channel == ChannelType.TELL:
            return f"tell:{self.tell_target.lower() if self.tell_target else 'unknown'}"
        else:
            return self.channel.value


@dataclass
class Conversation:
    """A conversation (channel or DM)."""
    id: str
    channel: ChannelType
    name: str  # Display name
    messages: list[ChatMessage] = field(default_factory=list)
    unread_count: int = 0

    @property
    def last_message(self) -> Optional[ChatMessage]:
        return self.messages[-1] if self.messages else None

    @property
    def last_activity(self) -> Optional[datetime]:
        return self.last_message.timestamp if self.last_message else None

    @property
    def preview_text(self) -> str:
        if not self.last_message:
            return "No messages"
        msg = self.last_message
        prefix = "You: " if msg.is_outgoing else ""
        content = msg.content[:40] + "..." if len(msg.content) > 40 else msg.content
        return prefix + content

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "channel": self.channel.value,
            "name": self.name,
            "messages": [m.to_dict() for m in self.messages[-2000:]],
        }

    @classmethod
    def from_dict(cls, d: dict) -> Conversation:
        messages = []
        for m in d.get("messages", []):
            try:
                messages.append(ChatMessage.from_dict(m))
            except Exception:
                pass  # Skip bad messages

        return cls(
            id=d["id"],
            channel=ChannelType(d["channel"]),
            name=d["name"],
            messages=messages,
        )


# =============================================================================
# TIMER DATA STRUCTURES
# =============================================================================


@dataclass
class SpellInfo:
    """Information about a spell from the spell database."""
    id: int
    name: str
    cast_on_you: str
    cast_on_other: str
    spell_fades: str
    duration_formula: int
    duration_base: int
    cast_time_ms: int = 0
    target_type: int = 0  # 5=single target (others), 6=self only
    beneficial: bool = True
    replaced_by: int = 0
    replacement_expansion: str = ""

    def get_duration_seconds(self, level: int) -> int:
        """Calculate duration for a given caster level."""
        from .duration import DurationFormula
        return DurationFormula.calculate(
            self.duration_formula, self.duration_base, level
        )

    @property
    def cast_time_seconds(self) -> float:
        return self.cast_time_ms / 1000.0

    @property
    def is_self_only(self) -> bool:
        return self.target_type == 6

    @property
    def is_beneficial(self) -> bool:
        return self.beneficial

    @property
    def has_landing_message(self) -> bool:
        return bool(self.cast_on_you or self.cast_on_other)

    @property
    def has_duration(self) -> bool:
        return not (self.duration_formula == 0 and self.duration_base == 0)


@dataclass
class ActiveTimer:
    """An active buff/debuff timer."""
    spell_name: str
    target: str
    end_time: datetime
    total_duration: int
    category: TimerCategory
    spell_info: Optional[SpellInfo] = None

    @property
    def remaining_seconds(self) -> float:
        return max(0, (self.end_time - datetime.now()).total_seconds())

    @property
    def percent_remaining(self) -> float:
        if self.total_duration <= 0:
            return 0
        return (self.remaining_seconds / self.total_duration) * 100

    @property
    def is_expired(self) -> bool:
        return datetime.now() >= self.end_time

    def remaining_at(self, ref: datetime) -> float:
        return max(0, (self.end_time - ref).total_seconds())

    def percent_at(self, ref: datetime) -> float:
        if self.total_duration <= 0:
            return 0
        return (self.remaining_at(ref) / self.total_duration) * 100

    def extend(self, duration: timedelta) -> None:
        self.end_time += duration

    @property
    def sort_key(self) -> tuple[int, datetime, str]:
        return (self.category.value, self.end_time, self.spell_name)


@dataclass
class PendingCast:
    """A spell that is currently being cast."""
    spell_name: str
    cast_time: datetime  # Wall clock time
    log_timestamp: datetime  # Log timestamp
    spell_info: Optional[SpellInfo] = None
    timer_created: bool = False
    item_name: Optional[str] = None  # Set if this is an item click


@dataclass
class TimePeriod:
    """A time period (for logout/zone tracking)."""
    start: datetime
    end: datetime

    @property
    def duration_seconds(self) -> float:
        return (self.end - self.start).total_seconds()

    def time_after(self, dt: datetime) -> float:
        if dt >= self.end:
            return 0
        if dt <= self.start:
            return self.duration_seconds
        return (self.end - dt).total_seconds()


# =============================================================================
# NOTIFICATION DATA STRUCTURE
# =============================================================================


@dataclass
class Notification:
    """A notification for the shared notification center."""
    type: NotificationType
    title: str
    message: str
    timestamp: datetime = field(default_factory=datetime.now)
    channel: Optional[ChannelType] = None
    conversation_id: Optional[str] = None  # For clicking to open conversation
    duration_ms: Optional[int] = None  # Override default duration
    icon: Optional[str] = None  # Emoji or icon identifier


# =============================================================================
# LOG ENTRY
# =============================================================================


@dataclass
class LogEntry:
    """A parsed log entry."""
    timestamp: datetime
    message: str


# =============================================================================
# DPS DATA
# =============================================================================


@dataclass
class DPSData:
    """DPS meter data."""
    active: bool
    ended: bool
    target: str
    num_targets: int
    duration: float
    players: list[dict]  # [{"name": str, "damage": int, "dps": float}, ...]
