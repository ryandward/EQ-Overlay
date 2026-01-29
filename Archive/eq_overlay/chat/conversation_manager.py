"""
Conversation manager - handles chat history and persistence.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..core.data import ChatMessage, Conversation, ChannelType
from ..config import Config


class ConversationManager:
    """
    Manages all conversations and persistence.
    
    Handles:
    - Channel conversations (guild, ooc, group, etc.)
    - DM conversations (tells)
    - Global aggregated view
    - JSON persistence
    """

    GLOBAL_ID = "_global_"

    def __init__(self, config: Config, character_name: str):
        self._config = config
        self._character_name = character_name
        self._conversations: dict[str, Conversation] = {}
        self._data_file = config.get_conversations_file(character_name)

        # Global view settings
        self._global_channels: set[str] = set(config.chat.global_channels)
        self._global_output_channel: str = "guild"

        # Create default channel conversations
        self._ensure_channel_conversation(ChannelType.GUILD, "Guild")
        self._ensure_channel_conversation(ChannelType.OOC, "OOC")
        self._ensure_channel_conversation(ChannelType.GROUP, "Group")
        self._ensure_channel_conversation(ChannelType.SHOUT, "Shout")
        self._ensure_channel_conversation(ChannelType.AUCTION, "Auction")
        self._ensure_channel_conversation(ChannelType.RANDOM, "Random")
        self._ensure_channel_conversation(ChannelType.WHO, "Who")

    def _ensure_channel_conversation(self, channel: ChannelType, name: str) -> None:
        """Ensure a channel conversation exists."""
        conv_id = channel.value
        if conv_id not in self._conversations:
            self._conversations[conv_id] = Conversation(
                id=conv_id,
                channel=channel,
                name=name,
            )

    def get_or_create_tell_conversation(self, player_name: str) -> Conversation:
        """Get or create a DM conversation with a player."""
        conv_id = f"tell:{player_name.lower()}"
        if conv_id not in self._conversations:
            self._conversations[conv_id] = Conversation(
                id=conv_id,
                channel=ChannelType.TELL,
                name=player_name.capitalize(),
            )
        return self._conversations[conv_id]

    # =========================================================================
    # GLOBAL VIEW
    # =========================================================================

    def get_global_channels(self) -> set[str]:
        """Get the set of channel IDs included in global view."""
        return self._global_channels.copy()

    def set_global_channels(self, channels: set[str]) -> None:
        """Set which channels are included in global view."""
        self._global_channels = channels.copy()

    def toggle_global_channel(self, channel_id: str) -> bool:
        """Toggle a channel in/out of global view. Returns new state."""
        if channel_id in self._global_channels:
            self._global_channels.discard(channel_id)
            return False
        else:
            self._global_channels.add(channel_id)
            return True

    def get_global_output_channel(self) -> str:
        """Get the default output channel for global view."""
        return self._global_output_channel

    def set_global_output_channel(self, channel_id: str) -> None:
        """Set the default output channel for global view."""
        self._global_output_channel = channel_id

    def get_global_messages(self, limit: int = 200) -> list[ChatMessage]:
        """Get merged messages from all global channels, sorted by time."""
        all_messages = []

        for channel_id in self._global_channels:
            if channel_id == "tell":
                # Include all tell conversations
                for conv in self._conversations.values():
                    if conv.channel == ChannelType.TELL:
                        all_messages.extend(conv.messages)
            else:
                conv = self._conversations.get(channel_id)
                if conv:
                    all_messages.extend(conv.messages)

        all_messages.sort(key=lambda m: m.timestamp)
        return all_messages[-limit:]

    def is_global_view(self, conv_id: str) -> bool:
        """Check if a conversation ID is the global view."""
        return conv_id == self.GLOBAL_ID

    # =========================================================================
    # MESSAGE HANDLING
    # =========================================================================

    def add_message(self, msg: ChatMessage) -> Optional[Conversation]:
        """Add a message to the appropriate conversation."""
        conv_id = msg.conversation_id

        if msg.channel == ChannelType.TELL:
            other_party = msg.tell_target
            if other_party:
                conv = self.get_or_create_tell_conversation(other_party)
            else:
                return None
        else:
            conv = self._conversations.get(conv_id)

        if conv:
            # Check for duplicate
            for existing in conv.messages:
                if (
                    existing.timestamp == msg.timestamp
                    and existing.sender == msg.sender
                    and existing.content == msg.content
                ):
                    return conv  # Already exists

            conv.messages.append(msg)

            # Trim old messages
            max_msgs = self._config.chat.max_messages_per_convo
            if len(conv.messages) > max_msgs:
                conv.messages = conv.messages[-max_msgs:]

        return conv

    def prepend_message(self, msg: ChatMessage) -> tuple[Optional[Conversation], bool]:
        """Add an older message to the beginning. Returns (conversation, was_added)."""
        conv_id = msg.conversation_id

        if msg.channel == ChannelType.TELL:
            other_party = msg.tell_target
            if other_party:
                conv = self.get_or_create_tell_conversation(other_party)
            else:
                return None, False
        else:
            conv = self._conversations.get(conv_id)

        if conv:
            # Check for duplicate
            for existing in conv.messages:
                if (
                    existing.timestamp == msg.timestamp
                    and existing.sender == msg.sender
                    and existing.content == msg.content
                ):
                    return conv, False

            conv.messages.insert(0, msg)
            return conv, True

        return conv, False

    def get_conversation(self, conv_id: str) -> Optional[Conversation]:
        """Get a conversation by ID."""
        if conv_id == self.GLOBAL_ID:
            return self._create_global_conversation()
        return self._conversations.get(conv_id)

    def _create_global_conversation(self) -> Conversation:
        """Create a virtual conversation for global view."""
        messages = self.get_global_messages(limit=500)
        return Conversation(
            id=self.GLOBAL_ID,
            channel=ChannelType.GUILD,  # Base channel (color overridden)
            name="Global",
            messages=messages,
        )

    def get_all_conversations(self) -> list[Conversation]:
        """Get all conversations sorted by type then activity."""
        convos = list(self._conversations.values())

        def sort_key(c):
            channel_order = {
                ChannelType.GUILD: 0,
                ChannelType.OOC: 1,
                ChannelType.GROUP: 2,
                ChannelType.SHOUT: 3,
                ChannelType.AUCTION: 4,
                ChannelType.RANDOM: 5,
                ChannelType.WHO: 6,
                ChannelType.TELL: 7,
            }
            order = channel_order.get(c.channel, 7)
            activity = c.last_activity
            if activity:
                return (order, -activity.timestamp())
            return (order, float("inf"))

        return sorted(convos, key=sort_key)

    def get_dm_conversations(self) -> list[Conversation]:
        """Get only DM (tell) conversations, sorted by activity."""
        dms = [c for c in self._conversations.values() if c.channel == ChannelType.TELL]

        def sort_key(c):
            activity = c.last_activity
            if activity:
                return -activity.timestamp()
            return float("inf")

        return sorted(dms, key=sort_key)

    # =========================================================================
    # PERSISTENCE
    # =========================================================================

    def load(self) -> bool:
        """Load conversations from disk. Returns True if data was loaded."""
        if not self._data_file.exists():
            return False

        try:
            with open(self._data_file, "r") as f:
                data = json.load(f)

            for conv_data in data.get("conversations", []):
                try:
                    conv = Conversation.from_dict(conv_data)
                    self._conversations[conv.id] = conv
                except Exception as e:
                    print(f"Skipping invalid conversation: {e}")

            # Load global settings
            if "global_channels" in data:
                self._global_channels = set(data["global_channels"])
            if "global_output_channel" in data:
                self._global_output_channel = data["global_output_channel"]

            self.sort_all_messages()
            return True

        except Exception as e:
            print(f"Error loading conversations: {e}")
            return False

    def has_data(self) -> bool:
        """Check if we have meaningful data (not just empty channels)."""
        for conv in self._conversations.values():
            if conv.messages:
                return True
        return False

    def get_latest_timestamp(self) -> Optional[datetime]:
        """Get the timestamp of the most recent message."""
        latest = None
        for conv in self._conversations.values():
            if conv.messages:
                msg_time = conv.messages[-1].timestamp
                if latest is None or msg_time > latest:
                    latest = msg_time
        return latest

    def save(self) -> None:
        """Save conversations to disk."""
        self.sort_all_messages()

        self._config.paths.data_dir.mkdir(parents=True, exist_ok=True)

        try:
            data = {
                "conversations": [c.to_dict() for c in self._conversations.values()],
                "global_channels": list(self._global_channels),
                "global_output_channel": self._global_output_channel,
            }
            with open(self._data_file, "w") as f:
                json.dump(data, f)
        except Exception as e:
            print(f"Error saving conversations: {e}")

    def sort_all_messages(self) -> None:
        """Sort messages in all conversations by timestamp."""
        for conv in self._conversations.values():
            conv.messages.sort(key=lambda m: m.timestamp)

    def mark_read(self, conv_id: str) -> None:
        """Mark a conversation as read."""
        conv = self._conversations.get(conv_id)
        if conv:
            conv.unread_count = 0

    def increment_unread(self, conv_id: str) -> None:
        """Increment unread count for a conversation."""
        conv = self._conversations.get(conv_id)
        if conv:
            conv.unread_count += 1
