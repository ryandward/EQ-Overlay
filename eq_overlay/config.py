"""
Configuration management for EQ Overlay.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class PathsConfig:
    log_dir: Path
    spells_file: Path
    whitelist_file: Path
    data_dir: Path
    learned_items_file: Optional[Path] = None

    @property
    def eq_dir(self) -> Path:
        return self.log_dir.parent

    @property
    def ini_path(self) -> Path:
        return self.eq_dir / "eqclient.ini"


@dataclass
class WindowConfig:
    side: str  # "left" or "right"
    width: int
    opacity: float
    sidebar_width: int = 100  # Only used by chat panel


@dataclass
class NotificationsConfig:
    position: str  # "top_center", "top_left", "top_right"
    max_visible: int
    default_duration_ms: int
    tell_duration_ms: int
    buff_warning_duration_ms: int
    play_sound_on_tell: bool
    width: int
    spacing: int


@dataclass
class ChatConfig:
    max_messages_per_convo: int
    history_scan_bytes: int
    global_channels: list[str]
    bold_messages: bool = True  # Whether chat bubble text is bold


@dataclass
class TimersConfig:
    history_hours: float
    cast_window_seconds: int
    update_interval_ms: int
    combat_timeout_seconds: int
    dps_meter_max_players: int


@dataclass
class BehaviorConfig:
    auto_hide_when_unfocused: bool
    auto_switch_character: bool


@dataclass
class FontConfig:
    family: str
    scale: float
    # Base sizes before scaling
    size_xxs: int = 8
    size_xs: int = 9
    size_sm: int = 10
    size_md: int = 11
    size_lg: int = 12
    size_xl: int = 13


@dataclass
class Config:
    """Main configuration container."""

    paths: PathsConfig
    server: str
    default_level: int
    chat_window: WindowConfig
    timers_window: WindowConfig
    notifications: NotificationsConfig
    chat: ChatConfig
    timers: TimersConfig
    behavior: BehaviorConfig
    font: FontConfig

    # Runtime state (not from config file)
    character_name: Optional[str] = None

    @classmethod
    def load(cls, config_path: Optional[Path] = None) -> Config:
        """Load configuration from JSON file."""
        if config_path is None:
            # Look in standard locations
            candidates = [
                Path.cwd() / "config.json",
                Path.home() / ".config" / "eq-overlay" / "config.json",
                Path(__file__).parent.parent / "config.json",
            ]
            for path in candidates:
                if path.exists():
                    config_path = path
                    break

        if config_path is None or not config_path.exists():
            raise FileNotFoundError(
                "No config.json found. Please create one from config.example.json"
            )

        with open(config_path, "r") as f:
            data = json.load(f)

        return cls._from_dict(data)

    @classmethod
    def _from_dict(cls, data: dict) -> Config:
        """Parse configuration from dictionary."""
        paths_data = data["paths"]
        learned_items = paths_data.get("learned_items_file")
        paths = PathsConfig(
            log_dir=Path(paths_data["log_dir"]).expanduser(),
            spells_file=Path(paths_data["spells_file"]).expanduser(),
            whitelist_file=Path(paths_data["whitelist_file"]).expanduser(),
            data_dir=Path(paths_data["data_dir"]).expanduser(),
            learned_items_file=Path(learned_items).expanduser() if learned_items else None,
        )

        chat_window = WindowConfig(
            side=data["windows"]["chat"]["side"],
            width=data["windows"]["chat"]["width"],
            opacity=data["windows"]["chat"]["opacity"],
            sidebar_width=data["windows"]["chat"].get("sidebar_width", 100),
        )
        timers_window = WindowConfig(
            side=data["windows"]["timers"]["side"],
            width=data["windows"]["timers"]["width"],
            opacity=data["windows"]["timers"]["opacity"],
        )
        notifications = NotificationsConfig(**data["notifications"])
        chat_data = data["chat"]
        chat = ChatConfig(
            max_messages_per_convo=chat_data["max_messages_per_convo"],
            history_scan_bytes=chat_data["history_scan_bytes"],
            global_channels=chat_data["global_channels"],
            bold_messages=chat_data.get("bold_messages", True),
        )
        timers = TimersConfig(**data["timers"])
        behavior = BehaviorConfig(**data["behavior"])
        
        # Font config with sensible defaults
        font_data = data.get("font", {})
        font = FontConfig(
            family=font_data.get("family", "DejaVu Sans"),
            scale=font_data.get("scale", 1.0),
            size_xxs=font_data.get("size_xxs", 8),
            size_xs=font_data.get("size_xs", 9),
            size_sm=font_data.get("size_sm", 10),
            size_md=font_data.get("size_md", 11),
            size_lg=font_data.get("size_lg", 12),
            size_xl=font_data.get("size_xl", 13),
        )

        return cls(
            paths=paths,
            server=data["server"],
            default_level=data["character"]["default_level"],
            chat_window=chat_window,
            timers_window=timers_window,
            notifications=notifications,
            chat=chat,
            timers=timers,
            behavior=behavior,
            font=font,
        )

    def get_conversations_file(self, character_name: str) -> Path:
        """Get path to conversation history JSON for a character."""
        return self.paths.data_dir / f"conversations_{character_name.lower()}.json"

    def get_learned_items_file(self) -> Path:
        """Get path to learned item cast times."""
        if self.paths.learned_items_file:
            return self.paths.learned_items_file
        return self.paths.data_dir / "learned_items.json"

    def get_settings_file(self) -> Path:
        """Get path to runtime settings."""
        return self.paths.data_dir / "settings.json"
