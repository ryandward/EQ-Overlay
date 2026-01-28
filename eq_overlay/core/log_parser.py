"""
Unified log parser for EQ logs.

Parses both chat messages and spell/combat events from the same log stream.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from .data import (
    ChatMessage,
    ChannelType,
    LogEntry,
)
from .eq_utils import decode_eq_text


class LogParser:
    """
    Parses EQ log lines into structured data.
    
    Handles:
    - Chat messages (guild, ooc, tells, etc.)
    - Spell casting and landing
    - Combat damage
    - Game state changes
    """

    # Timestamp pattern for all log lines
    TIMESTAMP_PATTERN = re.compile(r"^\[(\w+ \w+ \d+ \d+:\d+:\d+ \d+)\] (.*)$")
    TIMESTAMP_FORMAT = "%a %b %d %H:%M:%S %Y"

    # Chat patterns
    GUILD_OUT = re.compile(r"^You say to your guild, '(.+)'$")
    GUILD_IN = re.compile(r"^(\w+) tells the guild, '(.+)'$")

    OOC_OUT = re.compile(r"^You say out of character, '(.+)'$")
    OOC_IN = re.compile(r"^(\w+) says out of character, '(.+)'$")

    GROUP_OUT = re.compile(r"^You tell your party, '(.+)'$")
    GROUP_IN = re.compile(r"^(\w+) tells the group, '(.+)'$")

    SHOUT_OUT = re.compile(r"^You shout,? '(.+)'$")
    SHOUT_IN = re.compile(r"^(.+?) shouts,? '(.+)'$")

    AUCTION_OUT = re.compile(r"^You auction,? '(.+)'$")
    AUCTION_IN = re.compile(r"^(.+?) auctions,? '(.+)'$")

    TELL_IN = re.compile(r"^(\w+) tells you, '(.+)'$")
    TELL_OUT = re.compile(r"^You told (\w+),? '(?:\[queued\], )?(.+)'$")
    TELL_ARROW = re.compile(r"^(\w+) -> (\w+): (.+)$")

    SAY_OUT = re.compile(r"^You say, '(.+)'$")
    SAY_IN = re.compile(r"^(\w+) says, '(.+)'$")

    # Random roll patterns (two consecutive lines)
    RANDOM_ROLLER = re.compile(r"^\*\*A Magic Die is rolled by (\w+)\.$")
    RANDOM_RESULT = re.compile(r"^\*\*It could have been any number from (\d+) to (\d+), but this time it turned up a (\d+)\.$")

    # /who output patterns
    WHO_HEADER = re.compile(r"^Players on EverQuest:$")
    WHO_NO_MATCH = re.compile(r"^There are no players in EverQuest that match")

    # Spell patterns
    CASTING_PATTERN = re.compile(r"^You begin casting (.+)\.$")
    ITEM_GLOW_PATTERN = re.compile(r"^Your (.+) begins to glow\.$")
    SPELL_WORN_OFF_PATTERN = re.compile(r"^Your (.+) spell has worn off\.$")

    # Combat patterns
    DAMAGE_PATTERN = re.compile(
        r"^You (?:hit|slash|pierce|crush|bash|kick|punch|strike|slice|claw|bite|sting|maul|gore|smash|backstab) "
        r"(.+) for (\d+) points? of damage\.$"
    )
    NON_MELEE_PATTERN = re.compile(
        r"^(.+) was hit by non-melee for (\d+) points? of damage\.$"
    )
    OTHER_DAMAGE_PATTERN = re.compile(
        r"^(.+?) (?:hits|slashes|pierces|crushes|bashes|kicks|punches|strikes|slices|claws|bites|stings|mauls|gores|smashes|backstabs) "
        r"(.+) for (\d+) points? of damage\.$"
    )
    SLAIN_PATTERN = re.compile(r"^You have slain (.+)!$")
    OTHER_SLAIN_PATTERN = re.compile(r"^(.+) has been slain by")

    # Game state patterns
    MSG_LOADING = "LOADING, PLEASE WAIT"
    MSG_ENTERED = "You have entered"
    MSG_CAMP_START = "It will take you about 30 seconds to prepare your camp."
    MSG_CAMP_ABANDON = "You abandon your preparations to camp."
    MSG_WELCOME = "Welcome to EverQuest!"
    MSG_SLAIN = "You have been slain"
    MSG_AUTO_ATTACK_ON = "Auto attack on."
    MSG_AUTO_ATTACK_OFF = "Auto attack off."
    MSG_NO_TARGET = "You no longer have a target."

    # Buff warning messages
    MSG_LEVI_FADING = "You feel as if you are about to fall."
    MSG_INVIS_FADING = "You feel yourself starting to appear."
    MSG_ILLUSION_FADING = "You feel as if you are about to look like yourself again."

    # Pet/spam messages to filter
    PET_MESSAGES = frozenset({
        "following you, master.",
        "guarding with my life..oh splendid one.",
        "no longer taunting attackers, master.",
        "as you wish, oh great one.",
        "sorry to have failed you, oh great one.",
        "ahhh, i feel much better now...",
    })

    BLACKLISTED_MESSAGES = frozenset({
        "You feel quite amicable.",
    })

    CAST_FAILURE_MESSAGES = frozenset({
        "Your spell fizzles",
        "Your target resisted",
        "Your must first select a target",
        "Your spell is interrupted",
        "You cannot see your target",
        "Your target is out of range",
    })

    def __init__(self, character_name: str):
        self.character_name = character_name
        self._pending_roller: Optional[str] = None  # Track who rolled for random
        self._last_was_die_roll: bool = False  # Must be back-to-back entries
        self._who_lines: list[str] = []  # Accumulate /who output
        self._who_timestamp: Optional[datetime] = None

    def parse_line(self, line: str) -> Optional[LogEntry]:
        """Parse a raw log line into a LogEntry."""
        match = self.TIMESTAMP_PATTERN.match(line.strip())
        if not match:
            return None
        try:
            timestamp = datetime.strptime(match.group(1), self.TIMESTAMP_FORMAT)
            return LogEntry(timestamp=timestamp, message=match.group(2).strip())
        except ValueError:
            return None

    def _is_pet_spam(self, content: str) -> bool:
        """Check if message is pet spam or lifetap proc."""
        content_lower = content.lower()
        if content_lower in self.PET_MESSAGES:
            return True
        if content_lower.startswith("attacking ") and content_lower.endswith(" master."):
            return True
        return False

    def parse_chat_message(self, entry: LogEntry) -> Optional[ChatMessage]:
        """Parse a log entry into a chat message if applicable."""
        text = entry.message

        # Guild
        if m := self.GUILD_OUT.match(text):
            return ChatMessage(
                entry.timestamp, ChannelType.GUILD, "You",
                decode_eq_text(m.group(1)), is_outgoing=True
            )
        if m := self.GUILD_IN.match(text):
            return ChatMessage(
                entry.timestamp, ChannelType.GUILD, m.group(1),
                decode_eq_text(m.group(2))
            )

        # OOC
        if m := self.OOC_OUT.match(text):
            return ChatMessage(
                entry.timestamp, ChannelType.OOC, "You",
                decode_eq_text(m.group(1)), is_outgoing=True
            )
        if m := self.OOC_IN.match(text):
            return ChatMessage(
                entry.timestamp, ChannelType.OOC, m.group(1),
                decode_eq_text(m.group(2))
            )

        # Group
        if m := self.GROUP_OUT.match(text):
            return ChatMessage(
                entry.timestamp, ChannelType.GROUP, "You",
                decode_eq_text(m.group(1)), is_outgoing=True
            )
        if m := self.GROUP_IN.match(text):
            return ChatMessage(
                entry.timestamp, ChannelType.GROUP, m.group(1),
                decode_eq_text(m.group(2))
            )

        # Shout
        if m := self.SHOUT_OUT.match(text):
            return ChatMessage(
                entry.timestamp, ChannelType.SHOUT, "You",
                decode_eq_text(m.group(1)), is_outgoing=True
            )
        if m := self.SHOUT_IN.match(text):
            return ChatMessage(
                entry.timestamp, ChannelType.SHOUT, m.group(1),
                decode_eq_text(m.group(2))
            )

        # Auction
        if m := self.AUCTION_OUT.match(text):
            return ChatMessage(
                entry.timestamp, ChannelType.AUCTION, "You",
                decode_eq_text(m.group(1)), is_outgoing=True
            )
        if m := self.AUCTION_IN.match(text):
            return ChatMessage(
                entry.timestamp, ChannelType.AUCTION, m.group(1),
                decode_eq_text(m.group(2))
            )

        # Tells
        if m := self.TELL_IN.match(text):
            sender = m.group(1)
            content = decode_eq_text(m.group(2))
            if self._is_pet_spam(content):
                return None
            return ChatMessage(
                entry.timestamp, ChannelType.TELL, sender, content,
                is_outgoing=False, tell_target=sender
            )
        if m := self.TELL_OUT.match(text):
            recipient = m.group(1)
            return ChatMessage(
                entry.timestamp, ChannelType.TELL, "You",
                decode_eq_text(m.group(2)),
                is_outgoing=True, tell_target=recipient
            )
        if m := self.TELL_ARROW.match(text):
            sender, recipient, content = m.group(1), m.group(2), m.group(3)
            is_out = sender.lower() == self.character_name.lower()
            other = recipient if is_out else sender
            content = decode_eq_text(content)
            if not is_out and self._is_pet_spam(content):
                return None
            return ChatMessage(
                entry.timestamp, ChannelType.TELL, sender, content,
                is_outgoing=is_out, tell_target=other
            )

        # Say (local chat)
        if m := self.SAY_OUT.match(text):
            self._last_was_die_roll = False
            return ChatMessage(
                entry.timestamp, ChannelType.SAY, "You",
                decode_eq_text(m.group(1)), is_outgoing=True
            )
        if m := self.SAY_IN.match(text):
            self._last_was_die_roll = False
            content = decode_eq_text(m.group(2))
            if self._is_pet_spam(content):
                return None
            return ChatMessage(
                entry.timestamp, ChannelType.SAY, m.group(1), content
            )

        # Random roll (two consecutive back-to-back lines)
        # First line: **A Magic Die is rolled by Playername.
        if m := self.RANDOM_ROLLER.match(text):
            self._pending_roller = m.group(1)
            self._last_was_die_roll = True
            print(f"DEBUG RANDOM: Die roll by {self._pending_roller}, flag={self._last_was_die_roll}")
            return None  # Wait for result line
        
        # Second line: **It could have been any number from X to Y, but this time it turned up a Z.
        # MUST immediately follow the die roll line
        if m := self.RANDOM_RESULT.match(text):
            print(f"DEBUG RANDOM: Result line, flag={self._last_was_die_roll}, roller={self._pending_roller}")
            if self._last_was_die_roll and self._pending_roller:
                roller = self._pending_roller
                self._pending_roller = None
                self._last_was_die_roll = False
                low, high, result = m.group(1), m.group(2), m.group(3)
                is_me = roller.lower() == self.character_name.lower()
                print(f"DEBUG RANDOM: Creating message for {roller} rolled {result}")
                return ChatMessage(
                    entry.timestamp, ChannelType.RANDOM, roller,
                    f"{result} ({low}-{high})", is_outgoing=is_me
                )
            # Result without preceding die roll - ignore
            self._last_was_die_roll = False
            return None

        # Any other message breaks the die roll sequence
        self._last_was_die_roll = False
        return None

    def parse_who(self, entry: LogEntry) -> Optional[ChatMessage]:
        """Parse /who output. Lines are guaranteed contiguous."""
        text = entry.message
        
        # Start of WHO block
        if self.WHO_HEADER.match(text):
            self._who_lines = [text]
            self._who_timestamp = entry.timestamp
            return None
        
        # Standalone no-match (when filters return 0)
        if not self._who_lines and self.WHO_NO_MATCH.match(text):
            return ChatMessage(
                entry.timestamp, ChannelType.WHO, "Who",
                text, is_outgoing=False
            )
        
        # Accumulating - just check for end condition
        if self._who_lines:
            self._who_lines.append(text)
            
            # End condition: "There is/are X players" or "no players match"
            if text.startswith("There "):
                combined = "\n".join(self._who_lines)
                timestamp = self._who_timestamp or entry.timestamp
                self._who_lines = []
                self._who_timestamp = None
                return ChatMessage(
                    timestamp, ChannelType.WHO, "Who",
                    combined, is_outgoing=False
                )
            return None
        
        return None

    def parse_casting(self, entry: LogEntry) -> Optional[str]:
        """Parse casting start. Returns spell name or None."""
        if m := self.CASTING_PATTERN.match(entry.message):
            return m.group(1)
        return None

    def parse_item_glow(self, entry: LogEntry) -> Optional[str]:
        """Parse item use (begins to glow). Returns item name or None."""
        if m := self.ITEM_GLOW_PATTERN.match(entry.message):
            return m.group(1)
        return None

    def parse_spell_worn_off(self, entry: LogEntry) -> Optional[str]:
        """Parse spell wearing off. Returns spell name or None."""
        if m := self.SPELL_WORN_OFF_PATTERN.match(entry.message):
            return m.group(1)
        return None

    def parse_your_damage(self, entry: LogEntry) -> Optional[tuple[str, int]]:
        """Parse your melee damage. Returns (target, damage) or None."""
        if m := self.DAMAGE_PATTERN.match(entry.message):
            return (m.group(1), int(m.group(2)))
        return None

    def parse_non_melee_damage(self, entry: LogEntry) -> Optional[tuple[str, int]]:
        """Parse non-melee damage (spells/procs). Returns (target, damage) or None."""
        if m := self.NON_MELEE_PATTERN.match(entry.message):
            return (m.group(1), int(m.group(2)))
        return None

    def parse_other_damage(self, entry: LogEntry) -> Optional[tuple[str, str, int]]:
        """Parse other player/pet damage. Returns (attacker, target, damage) or None."""
        if m := self.OTHER_DAMAGE_PATTERN.match(entry.message):
            return (m.group(1), m.group(2), int(m.group(3)))
        return None

    def parse_you_slain(self, entry: LogEntry) -> Optional[str]:
        """Parse 'You have slain X'. Returns target name or None."""
        if m := self.SLAIN_PATTERN.match(entry.message):
            return m.group(1)
        return None

    def parse_other_slain(self, entry: LogEntry) -> bool:
        """Check if something was slain by someone else."""
        return bool(self.OTHER_SLAIN_PATTERN.match(entry.message))

    def is_cast_failure(self, entry: LogEntry) -> bool:
        """Check if message indicates a cast failure."""
        return any(msg in entry.message for msg in self.CAST_FAILURE_MESSAGES)

    def is_blacklisted(self, entry: LogEntry) -> bool:
        """Check if message should be ignored."""
        return entry.message in self.BLACKLISTED_MESSAGES

    def is_death(self, entry: LogEntry) -> bool:
        """Check if the player died."""
        return self.MSG_SLAIN in entry.message

    def is_zone_change(self, entry: LogEntry) -> bool:
        """Check if entering a new zone."""
        return entry.message.startswith(self.MSG_ENTERED)

    def is_camp_start(self, entry: LogEntry) -> bool:
        """Check if camping started."""
        return entry.message == self.MSG_CAMP_START

    def is_camp_abandon(self, entry: LogEntry) -> bool:
        """Check if camping was abandoned."""
        return entry.message == self.MSG_CAMP_ABANDON

    def is_loading(self, entry: LogEntry) -> bool:
        """Check if loading screen."""
        return self.MSG_LOADING in entry.message

    def is_welcome(self, entry: LogEntry) -> bool:
        """Check for login welcome message."""
        return entry.message.startswith(self.MSG_WELCOME)

    def is_buff_warning(self, entry: LogEntry) -> Optional[str]:
        """Check for buff fading warning. Returns buff type or None."""
        msg = entry.message
        if msg == self.MSG_LEVI_FADING:
            return "levitation"
        if msg == self.MSG_INVIS_FADING:
            return "invisibility"
        if msg == self.MSG_ILLUSION_FADING:
            return "illusion"
        return None
