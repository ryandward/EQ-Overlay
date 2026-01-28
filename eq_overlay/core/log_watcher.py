"""
Unified log watcher - monitors EQ log file and dispatches events.
"""

from __future__ import annotations

import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Callable

from .data import LogEntry, ChatMessage, TimePeriod
from .log_parser import LogParser
from .signals import Signals
from ..config import Config


class LogWatcher:
    """
    Watches an EQ log file and dispatches parsed events via signals.
    
    This is the single source of truth for log events - both chat and
    timer systems subscribe to the same watcher.
    """

    def __init__(
        self,
        log_file: Path,
        character_name: str,
        signals: Signals,
        config: Config,
    ):
        self.log_file = log_file
        self.character_name = character_name
        self._signals = signals
        self._config = config
        self._parser = LogParser(character_name)

        self._running = False
        self._file_size = 0
        self._scanned_to_position = 0
        self._last_timestamp: Optional[datetime] = None

        # Callbacks for extensibility (timer system uses these)
        self._on_entry_callbacks: list[Callable[[LogEntry], None]] = []

    @property
    def parser(self) -> LogParser:
        """Access the log parser."""
        return self._parser

    def add_entry_callback(self, callback: Callable[[LogEntry], None]) -> None:
        """Add a callback to be called for each log entry."""
        self._on_entry_callbacks.append(callback)

    def remove_entry_callback(self, callback: Callable[[LogEntry], None]) -> None:
        """Remove an entry callback."""
        if callback in self._on_entry_callbacks:
            self._on_entry_callbacks.remove(callback)

    def stop(self) -> None:
        """Stop watching."""
        self._running = False

    def watch(self) -> None:
        """Main watch loop - call from a thread."""
        if not self.log_file.exists():
            self._signals.log_message.emit(f"Log not found: {self.log_file}")
            return

        self._running = True
        self._signals.log_message.emit(f"Watching: {self.log_file.name}")

        try:
            with open(self.log_file, "r", encoding="latin-1") as f:
                # Seek to end
                f.seek(0, 2)

                while self._running:
                    line = f.readline()
                    if not line:
                        time.sleep(0.1)
                        continue

                    self._process_line(line)

        except Exception as e:
            self._signals.log_message.emit(f"Watcher error: {e}")
            self._signals.status_changed.emit(f"Error: {e}")

    def _process_line(self, line: str) -> None:
        """Process a single log line."""
        entry = self._parser.parse_line(line)
        if not entry:
            return

        self._last_timestamp = entry.timestamp

        # Dispatch to all callbacks first (for timers)
        for callback in self._on_entry_callbacks:
            try:
                callback(entry)
            except Exception as e:
                print(f"Entry callback error: {e}")

        # Parse chat message
        if chat_msg := self._parser.parse_chat_message(entry):
            self._signals.chat_message_received.emit(chat_msg)
        # Parse /who output
        elif who_msg := self._parser.parse_who(entry):
            self._signals.chat_message_received.emit(who_msg)

    # =========================================================================
    # HISTORY LOADING - CHAT
    # =========================================================================

    def load_chat_history(
        self,
        max_channel_msgs: int = 10000,
        max_dm_convos: int = 500,
    ) -> list[ChatMessage]:
        """
        Load chat history by message count.
        
        Scans backwards until:
        - Each channel has max_channel_msgs messages (or hit beginning)
        - Found max_dm_convos unique DM conversations
        """
        from .data import ChannelType

        messages = []
        channel_counts = {
            ChannelType.GUILD: 0,
            ChannelType.OOC: 0,
            ChannelType.GROUP: 0,
            ChannelType.SHOUT: 0,
            ChannelType.AUCTION: 0,
        }
        dm_conversations: set[str] = set()

        def have_enough():
            channels_full = all(c >= max_channel_msgs for c in channel_counts.values())
            dms_full = len(dm_conversations) >= max_dm_convos
            return channels_full and dms_full

        try:
            with open(self.log_file, "r", encoding="latin-1") as f:
                f.seek(0, 2)
                self._file_size = f.tell()

                chunk_size = 2 * 1024 * 1024  # 2MB chunks
                end_pos = self._file_size

                while end_pos > 0 and not have_enough():
                    start_pos = max(0, end_pos - chunk_size)
                    f.seek(start_pos)

                    if start_pos > 0:
                        f.readline()  # Skip partial line

                    chunk_start = f.tell()

                    # Read this chunk
                    chunk_messages = []
                    while f.tell() < end_pos:
                        line = f.readline()
                        if not line:
                            break
                        if entry := self._parser.parse_line(line):
                            if msg := self._parser.parse_chat_message(entry):
                                chunk_messages.append(msg)

                    # Process chunk (newest first for counting)
                    for msg in reversed(chunk_messages):
                        if msg.channel == ChannelType.TELL:
                            target = msg.tell_target.lower() if msg.tell_target else "unknown"
                            if target in dm_conversations or len(dm_conversations) < max_dm_convos:
                                dm_conversations.add(target)
                                messages.append(msg)
                        else:
                            if channel_counts.get(msg.channel, 0) < max_channel_msgs:
                                channel_counts[msg.channel] = channel_counts.get(msg.channel, 0) + 1
                                messages.append(msg)

                    end_pos = chunk_start

                self._scanned_to_position = end_pos

        except Exception as e:
            print(f"Error loading chat history: {e}")

        # Reverse so oldest first
        messages.reverse()
        return messages

    def load_chat_history_since(self, since: datetime) -> list[ChatMessage]:
        """Load all chat messages since a given timestamp."""
        messages = []
        log_pattern = re.compile(r"^\[(\w+ \w+ \d+ \d+:\d+:\d+ \d+)\]")

        try:
            with open(self.log_file, "r", encoding="latin-1") as f:
                f.seek(0, 2)
                self._file_size = f.tell()

                chunk_size = 2 * 1024 * 1024
                end_pos = self._file_size
                start_read_pos = 0

                # Find where to start reading
                while end_pos > 0:
                    start_pos = max(0, end_pos - chunk_size)
                    f.seek(start_pos)

                    if start_pos > 0:
                        f.readline()

                    chunk_start = f.tell()
                    first_line = f.readline()

                    if first_line:
                        match = log_pattern.match(first_line.strip())
                        if match:
                            try:
                                ts = datetime.strptime(
                                    match.group(1), "%a %b %d %H:%M:%S %Y"
                                )
                                if ts < since:
                                    start_read_pos = chunk_start
                                    break
                            except ValueError:
                                pass

                    end_pos = chunk_start

                # Read forward from start_read_pos
                f.seek(start_read_pos)
                if start_read_pos > 0:
                    f.readline()

                for line in f:
                    if entry := self._parser.parse_line(line):
                        if entry.timestamp >= since:
                            if msg := self._parser.parse_chat_message(entry):
                                messages.append(msg)

        except Exception as e:
            print(f"Error loading chat history since {since}: {e}")

        return messages

    # =========================================================================
    # HISTORY LOADING - RAW ENTRIES (for timers)
    # =========================================================================

    def load_raw_history(self, hours: float = 3.0) -> list[LogEntry]:
        """Load raw log entries for the past N hours."""
        entries = []
        cutoff = datetime.now() - timedelta(hours=hours)

        try:
            with open(self.log_file, "r", encoding="latin-1") as f:
                f.seek(0, 2)
                file_size = f.tell()

                # Scan backwards to find start point
                chunk_size = 2 * 1024 * 1024
                end_pos = file_size
                start_read_pos = 0

                while end_pos > 0:
                    start_pos = max(0, end_pos - chunk_size)
                    f.seek(start_pos)

                    if start_pos > 0:
                        f.readline()

                    chunk_start = f.tell()
                    first_line = f.readline()

                    if first_line:
                        if entry := self._parser.parse_line(first_line):
                            if entry.timestamp < cutoff:
                                start_read_pos = chunk_start
                                break

                    end_pos = chunk_start

                # Read forward
                f.seek(start_read_pos)
                if start_read_pos > 0:
                    f.readline()

                for line in f:
                    if entry := self._parser.parse_line(line):
                        if entry.timestamp >= cutoff:
                            entries.append(entry)

        except Exception as e:
            print(f"Error loading raw history: {e}")

        return entries

    def find_logout_periods(self, entries: list[LogEntry]) -> list[TimePeriod]:
        """Find periods where player was logged out (for timer adjustment)."""
        periods = []
        last_timestamp: Optional[datetime] = None

        for entry in entries:
            if last_timestamp:
                gap = (entry.timestamp - last_timestamp).total_seconds()
                # If gap > 5 minutes, assume logout
                if gap > 300:
                    periods.append(TimePeriod(last_timestamp, entry.timestamp))
            last_timestamp = entry.timestamp

        return periods

    def find_zone_periods(self, entries: list[LogEntry]) -> list[TimePeriod]:
        """Find periods where player was zoning (loading screen)."""
        periods = []
        loading_start: Optional[datetime] = None

        for entry in entries:
            if self._parser.is_loading(entry):
                if loading_start is None:
                    loading_start = entry.timestamp
            elif loading_start is not None:
                # Zoning ended
                periods.append(TimePeriod(loading_start, entry.timestamp))
                loading_start = None

        return periods


def discover_characters(config: Config) -> list[tuple[str, Path, datetime]]:
    """
    Discover available character log files.
    
    Returns list of (character_name, log_path, last_modified) sorted by most recent.
    """
    if not config.paths.log_dir.exists():
        return []

    logs = []
    for path in config.paths.log_dir.glob(f"eqlog_*_{config.server}.txt"):
        match = re.match(r"eqlog_([^_]+)_", path.name)
        if match:
            try:
                mtime = datetime.fromtimestamp(path.stat().st_mtime)
                logs.append((match.group(1), path, mtime))
            except OSError:
                continue

    return sorted(logs, key=lambda x: x[2], reverse=True)


def find_character_log(name: str, config: Config) -> Optional[tuple[str, Path]]:
    """Find a specific character's log file."""
    for char_name, path, _ in discover_characters(config):
        if char_name.lower() == name.lower():
            return (char_name, path)
    return None
