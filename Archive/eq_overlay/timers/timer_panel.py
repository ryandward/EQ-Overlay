"""
Timer panel - spell timers and DPS meter window.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional
import json

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QScrollArea,
    QFrame,
    QMenu,
    QLabel,
)

from ..core.data import (
    ActiveTimer, TimerCategory, PendingCast, LogEntry,
    Notification, NotificationType,
)
from ..core.signals import Signals
from ..core.log_watcher import LogWatcher
from ..config import Config
from ..ui.theme import Theme
from ..ui.base_window import BaseOverlayWindow
from .spell_database import SpellDatabase
from .timer_manager import TimerManager
from .widgets import TimerBarWidget, CastingBarWidget, DPSMeterWidget, TargetBuffsRow


class TimerPanel(BaseOverlayWindow):
    """
    Timer panel window.
    
    Shows:
    - Casting bar
    - Active buff/debuff timers
    - DPS meter
    """

    MAX_TIMER_BARS = 20

    def __init__(
        self,
        signals: Signals,
        config: Config,
        spell_db: SpellDatabase,
        timer_mgr: TimerManager,
        log_watcher: LogWatcher,
        character_name: str,
    ):
        super().__init__(
            f"EQ Timers - {character_name}",
            config.timers_window,
            config,
            None,
        )

        self._signals = signals
        self._spell_db = spell_db
        self._timer_mgr = timer_mgr
        self._log_watcher = log_watcher
        self._character_name = character_name
        self._level = config.default_level

        # Casting state
        self._pending_cast: Optional[PendingCast] = None
        self._item_cast_times: dict[str, int] = {}
        self._loading_history = False
        self._last_entry_was_cast = False  # Track if previous log entry was a cast

        # DPS state
        self._combat_active = False
        self._combat_targets: set[str] = set()
        self._combat_start: Optional[datetime] = None
        self._combat_damage: dict[str, int] = {}
        self._last_damage_time: Optional[datetime] = None

        # Build UI
        self._build_ui()

        # Connect signals
        signals.timer_updated.connect(self._refresh_timers)
        signals.dps_updated.connect(self._dps_meter.update_dps)

        # Register log entry callback
        log_watcher.add_entry_callback(self._process_log_entry)

        # Update timer
        self._update_timer = QTimer(self)
        self._update_timer.timeout.connect(self._on_update)
        self._update_timer.start(config.timers.update_interval_ms)

        # Combat timeout timer
        self._combat_timer = QTimer(self)
        self._combat_timer.timeout.connect(self._check_combat_timeout)
        self._combat_timer.start(1000)

        # Load learned items
        self._load_learned_items()

    def _build_ui(self) -> None:
        """Build the timer panel UI."""
        # Use the container's content layout from base class
        layout = QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        self._content_layout.addLayout(layout)

        # Casting bar
        self._casting_bar = CastingBarWidget()
        layout.addWidget(self._casting_bar)

        # Separator
        sep1 = QFrame()
        sep1.setFixedHeight(1)
        sep1.setStyleSheet("background-color: rgba(60, 60, 80, 150);")
        layout.addWidget(sep1)

        # === YOUR BUFFS SECTION ===
        self._your_buffs_label = QLabel("Your Buffs")
        self._your_buffs_label.setFixedHeight(18)
        self._your_buffs_label.setStyleSheet("""
            color: rgba(150, 180, 200, 200);
            font-size: 10px;
            font-weight: bold;
            padding: 2px 4px;
        """)
        layout.addWidget(self._your_buffs_label)

        # Timer bars (single scroll area for self + others)
        timer_scroll = QScrollArea()
        timer_scroll.setWidgetResizable(True)
        timer_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        timer_scroll.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical { width: 4px; background: transparent; }
            QScrollBar::handle:vertical { background: rgba(100, 100, 120, 0.5); border-radius: 2px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)

        timer_container = QWidget()
        timer_container.setStyleSheet("background: transparent;")
        self._timer_layout = QVBoxLayout(timer_container)
        self._timer_layout.setContentsMargins(0, 0, 0, 0)
        self._timer_layout.setSpacing(2)

        # Pre-create timer bars for self-buffs
        self._timer_bars: list[TimerBarWidget] = []
        for _ in range(self.MAX_TIMER_BARS):
            bar = TimerBarWidget()
            self._timer_bars.append(bar)
            self._timer_layout.addWidget(bar)

        # Separator before others (hidden when no others)
        self._others_separator = QFrame()
        self._others_separator.setFixedHeight(1)
        self._others_separator.setStyleSheet("background-color: rgba(60, 60, 80, 150);")
        self._others_separator.hide()
        self._timer_layout.addWidget(self._others_separator)

        # Label for others section (hidden when no others)
        self._others_buffs_label = QLabel("Buffs on Others")
        self._others_buffs_label.setFixedHeight(18)
        self._others_buffs_label.setStyleSheet("""
            color: rgba(150, 180, 200, 200);
            font-size: 10px;
            font-weight: bold;
            padding: 2px 4px;
        """)
        self._others_buffs_label.hide()
        self._timer_layout.addWidget(self._others_buffs_label)

        # Container for target rows (will be populated dynamically)
        self._others_container = QWidget()
        self._others_container.setStyleSheet("background: transparent;")
        self._others_layout = QVBoxLayout(self._others_container)
        self._others_layout.setContentsMargins(0, 0, 0, 0)
        self._others_layout.setSpacing(4)
        self._timer_layout.addWidget(self._others_container)

        self._timer_layout.addStretch()
        timer_scroll.setWidget(timer_container)
        layout.addWidget(timer_scroll, 1)

        # Track target rows
        self._target_rows: dict[str, TargetBuffsRow] = {}

        # Separator before DPS
        sep2 = QFrame()
        sep2.setFixedHeight(1)
        sep2.setStyleSheet("background-color: rgba(60, 60, 80, 150);")
        layout.addWidget(sep2)

        # DPS meter
        self._dps_meter = DPSMeterWidget()
        layout.addWidget(self._dps_meter)

    def _on_update(self) -> None:
        """Periodic update for timers and casting bar."""
        # Update casting bar
        if self._pending_cast:
            spell_name = self._pending_cast.spell_name
            item_name = self._pending_cast.item_name

            if item_name and item_name in self._item_cast_times:
                cast_time_ms = self._item_cast_times[item_name]
                display_name = item_name
            else:
                cast_time_ms = self._spell_db.get_cast_time(spell_name)
                display_name = item_name if item_name else spell_name

            if cast_time_ms > 0:
                elapsed_ms = (datetime.now() - self._pending_cast.cast_time).total_seconds() * 1000
                if elapsed_ms <= cast_time_ms + 500:
                    self._casting_bar.set_casting(display_name, elapsed_ms, cast_time_ms)
                else:
                    self._casting_bar.clear()
            else:
                self._casting_bar.clear()
        else:
            self._casting_bar.clear()

        # Check for expired timers
        expired = self._timer_mgr.check_expired()

        # Refresh timer display
        self._refresh_timers()

    def _refresh_timers(self) -> None:
        """Update timer displays - bars for self, then others below."""
        timers = self._timer_mgr.get_all()

        # Separate self-buffs from buffs on others
        self_timers = []
        others_timers: dict[str, list[ActiveTimer]] = {}

        for timer in timers:
            if timer.target == "You":
                self_timers.append(timer)
            else:
                if timer.target not in others_timers:
                    others_timers[timer.target] = []
                others_timers[timer.target].append(timer)

        # Update self-buff bars (hide unused ones)
        for i, bar in enumerate(self._timer_bars):
            if i < len(self_timers):
                bar.set_timer(self_timers[i])
                bar.show()
            else:
                bar.set_timer(None)
                bar.hide()

        # Update label visibility
        self._your_buffs_label.setVisible(len(self_timers) > 0)
        
        # Show/hide others section
        has_others = len(others_timers) > 0
        self._others_separator.setVisible(has_others)
        self._others_buffs_label.setVisible(has_others)

        # Update others section - create/update/remove target rows
        current_targets = set(others_timers.keys())
        existing_targets = set(self._target_rows.keys())

        # Remove rows for targets no longer present
        for target in existing_targets - current_targets:
            row = self._target_rows.pop(target)
            self._others_layout.removeWidget(row)
            row.deleteLater()

        # Add/update rows for current targets
        for target, target_timers in others_timers.items():
            if target not in self._target_rows:
                # Create new row
                row = TargetBuffsRow(target)
                self._target_rows[target] = row
                self._others_layout.addWidget(row)

            self._target_rows[target].update_timers(target_timers)

    def _process_log_entry(self, entry: LogEntry) -> None:
        """Process a log entry for timer and DPS tracking."""
        parser = self._log_watcher.parser
        msg = entry.message
        
        # Save previous state before we potentially overwrite it
        prev_was_cast = self._last_entry_was_cast
        self._last_entry_was_cast = False  # Reset - only cast will set True

        # Check for blacklisted/ignored
        if parser.is_blacklisted(entry):
            return

        # Death clears all timers
        if parser.is_death(entry):
            self._timer_mgr.clear()
            self._end_combat()
            return

        # Cast failure
        if parser.is_cast_failure(entry):
            self._pending_cast = None
            return

        # Casting started
        if spell_name := parser.parse_casting(entry):
            spell_info = self._spell_db.get_by_name(spell_name)
            self._pending_cast = PendingCast(
                spell_name=spell_name,
                cast_time=datetime.now(),
                log_timestamp=entry.timestamp,
                spell_info=spell_info,
            )
            self._last_entry_was_cast = True  # Mark that THIS entry was a cast
            return

        # Item glow (click) - MUST be the very next log line after cast to be associated
        if item_name := parser.parse_item_glow(entry):
            if self._pending_cast and not self._pending_cast.item_name:
                # Only associate if the cast was the previous log entry we processed
                if prev_was_cast:
                    self._pending_cast.item_name = item_name
                # If cast wasn't the previous entry, they're unrelated
                # (player is casting a spell while clicking an item)
            
            # For instant-cast items (no "You begin casting" message),
            # create pending cast if we know this item from learned_items.json
            if not self._pending_cast:
                spell_name = self._get_item_spell_name(item_name)
                if spell_name:
                    spell_info = self._spell_db.get_by_name(spell_name)
                    self._pending_cast = PendingCast(
                        spell_name=spell_name,
                        cast_time=datetime.now(),
                        log_timestamp=entry.timestamp,
                        item_name=item_name,
                        spell_info=spell_info,
                    )
            return

        # Spell faded
        if fades_list := self._spell_db.find_by_fades(msg):
            for spell in fades_list:
                self._timer_mgr.remove(spell.name, "You")
            return

        # Spell worn off
        if spell_name := parser.parse_spell_worn_off(entry):
            self._timer_mgr.remove(spell_name, "You")
            return

        # Spell landing (cast on you)
        if spells := self._spell_db.find_by_cast_on_you(msg):
            is_self_cast = False
            prefer_name = None
            item_name = None
            cast_start = None

            if self._pending_cast:
                elapsed = (entry.timestamp - self._pending_cast.log_timestamp).total_seconds()
                if elapsed < self._app_config.timers.cast_window_seconds:
                    # Check if this matches our pending cast
                    for s in spells:
                        if s.name == self._pending_cast.spell_name:
                            is_self_cast = True
                            prefer_name = s.name
                            item_name = self._pending_cast.item_name
                            cast_start = self._pending_cast.cast_time
                            self._pending_cast = None
                            break

            # Learn item cast time (only during live watching)
            if item_name and cast_start:
                elapsed_ms = int((datetime.now() - cast_start).total_seconds() * 1000)
                # Round to nearest second for cleaner data
                rounded_ms = round(elapsed_ms / 1000) * 1000
                if rounded_ms > 0:
                    self._item_cast_times[item_name] = rounded_ms
                    print(f"Learned item cast time: {item_name} = {rounded_ms}ms")

            if spell := self._spell_db.best_match(spells, prefer_name):
                duration = spell.get_duration_seconds(self._level)
                if duration > 0:
                    category = TimerCategory.SELF_BUFF if is_self_cast else TimerCategory.RECEIVED_BUFF
                    timer = ActiveTimer(
                        spell_name=spell.name,
                        target="You",
                        end_time=datetime.now() + timedelta(seconds=duration),
                        total_duration=duration,
                        category=category,
                        spell_info=spell,
                    )
                    self._timer_mgr.add(timer)
            return

        # Spell landing on OTHER (e.g., "Soandso's feet leave the ground")
        self._check_cast_on_other(msg)

        # Buff warning
        if buff_type := parser.is_buff_warning(entry):
            notif = Notification(
                type=NotificationType.BUFF_WARNING,
                title=f"{buff_type.title()} Fading",
                message=f"Your {buff_type} is about to wear off!",
                icon="⚠️",
            )
            self._signals.notification_requested.emit(notif)
            return

        # Combat damage tracking
        if dmg := parser.parse_your_damage(entry):
            target, amount = dmg
            self._add_damage("You", amount, target)
            return

        if dmg := parser.parse_non_melee_damage(entry):
            target, amount = dmg
            self._add_damage("You", amount, target)
            return

        if dmg := parser.parse_other_damage(entry):
            attacker, target, amount = dmg
            self._add_damage(attacker, amount, target)
            return

        # Kill tracking
        if target := parser.parse_you_slain(entry):
            self._end_combat()
            return

        if parser.parse_other_slain(entry):
            self._end_combat()
            return

    # =========================================================================
    # CAST ON OTHER
    # =========================================================================

    def _check_cast_on_other(self, msg: str) -> None:
        """Check if message is a spell landing on someone else (that YOU cast)."""
        if not self._pending_cast:
            print(f"DEBUG _check_cast_on_other: no pending cast for msg='{msg}'")
            return
        
        print(f"DEBUG _check_cast_on_other: checking msg='{msg}' with pending='{self._pending_cast.spell_name}'")

        # Check all cast_on_other suffixes
        for suffix, spells in self._spell_db._by_cast_on_other.items():
            if not suffix or not msg.endswith(suffix):
                continue

            # Extract target name (everything before the suffix)
            target = msg[: -len(suffix)]
            if not target or target.startswith(" "):
                continue

            print(f"DEBUG: cast_on_other match - msg='{msg}', suffix='{suffix}', target='{target}'")
            print(f"DEBUG: pending_cast spell='{self._pending_cast.spell_name}'")

            # Check if this matches our pending cast
            prefer = None
            elapsed = (datetime.now() - self._pending_cast.cast_time).total_seconds()
            print(f"DEBUG: elapsed={elapsed:.2f}s, window={self._app_config.timers.cast_window_seconds}s")
            if elapsed < self._app_config.timers.cast_window_seconds:
                for s in spells:
                    print(f"DEBUG: checking spell '{s.name}' against pending '{self._pending_cast.spell_name}'")
                    if s.name == self._pending_cast.spell_name:
                        prefer = s.name
                        break

            if not prefer:
                print(f"DEBUG: no prefer match, continuing")
                continue

            print(f"DEBUG: MATCH FOUND! prefer='{prefer}', clearing pending cast")
            
            # Clear pending cast and create timer
            item_name = self._pending_cast.item_name
            cast_start = self._pending_cast.cast_time
            self._pending_cast = None

            spell = self._spell_db.best_match(spells, prefer)
            if not spell:
                print(f"DEBUG: best_match returned None")
                continue

            # Learn item cast time
            if item_name and cast_start:
                elapsed_ms = int((datetime.now() - cast_start).total_seconds() * 1000)
                rounded_ms = round(elapsed_ms / 1000) * 1000
                if rounded_ms > 0:
                    self._item_cast_times[item_name] = rounded_ms

            duration = spell.get_duration_seconds(self._level)
            print(f"DEBUG: spell={spell.name}, duration={duration}")
            if duration <= 0:
                print(f"DEBUG: duration <= 0, skipping")
                continue

            # Use spell's beneficial flag to determine category
            category = (
                TimerCategory.OTHER_BUFF
                if spell.is_beneficial
                else TimerCategory.DEBUFF
            )

            print(f"DEBUG: Creating timer for {spell.name} on {target}, duration={duration}s")
            timer = ActiveTimer(
                spell_name=spell.name,
                target=target,
                end_time=datetime.now() + timedelta(seconds=duration),
                total_duration=duration,
                category=category,
                spell_info=spell,
            )
            self._timer_mgr.add(timer)
            return

    # =========================================================================
    # DPS TRACKING
    # =========================================================================

    def _add_damage(self, player: str, amount: int, target: str = "") -> None:
        """Add damage to current combat."""
        if not self._combat_active:
            self._combat_active = True
            self._combat_start = datetime.now()
            self._combat_damage = {}
            self._combat_targets = set()

        if target:
            self._combat_targets.add(target)

        self._combat_damage[player] = self._combat_damage.get(player, 0) + amount
        self._last_damage_time = datetime.now()
        self._emit_dps()

    def _end_combat(self) -> None:
        """End current combat."""
        if self._combat_active:
            self._emit_dps(final=True)
            self._combat_active = False
            self._last_damage_time = None

    def _check_combat_timeout(self) -> None:
        """End combat if no damage for N seconds."""
        if self._combat_active and self._last_damage_time:
            timeout = self._app_config.timers.combat_timeout_seconds
            if (datetime.now() - self._last_damage_time).total_seconds() > timeout:
                self._end_combat()

    def _emit_dps(self, final: bool = False) -> None:
        """Emit DPS data."""
        if not self._combat_start:
            return

        duration = (datetime.now() - self._combat_start).total_seconds()
        if duration <= 0:
            duration = 0.1

        players = []
        for player, damage in self._combat_damage.items():
            dps = damage / duration
            players.append({"name": player, "damage": damage, "dps": dps})

        players.sort(key=lambda x: x["damage"], reverse=True)

        num_targets = len(self._combat_targets)
        if num_targets == 0:
            target_display = "Combat"
        elif num_targets == 1:
            target_display = list(self._combat_targets)[0]
        else:
            target_display = f"{num_targets} targets"

        self._signals.dps_updated.emit({
            "active": not final,
            "ended": final,
            "target": target_display,
            "num_targets": num_targets,
            "duration": duration,
            "players": players,
        })

    # =========================================================================
    # LEARNED ITEMS
    # =========================================================================

    def _load_learned_items(self) -> None:
        """Load learned item cast times and spell mappings."""
        path = self._app_config.get_learned_items_file()
        if not path.exists():
            return

        try:
            with open(path, "r") as f:
                data = json.load(f)

            self._learned_items = data  # Store full data for spell matching
            
            for item_name, info in data.items():
                # Get best cast time (most frequently observed)
                if "cast_times_ms" in info and info["cast_times_ms"]:
                    cast_times = info["cast_times_ms"]
                    if isinstance(cast_times, dict) and cast_times:
                        best_time = max(cast_times.items(), key=lambda x: int(x[1]))[0]
                        self._item_cast_times[item_name] = int(best_time)

            print(f"Loaded {len(self._item_cast_times)} item cast times, {len(self._learned_items)} item definitions")
        except Exception as e:
            print(f"Could not load learned items: {e}")

    def _get_item_spell_name(self, item_name: str) -> Optional[str]:
        """Get the spell name for a learned item."""
        if hasattr(self, '_learned_items') and item_name in self._learned_items:
            return self._learned_items[item_name].get("spell_name")
        return None

    def _save_learned_items(self) -> None:
        """Save learned item cast times."""
        path = self._app_config.get_learned_items_file()
        path.parent.mkdir(parents=True, exist_ok=True)

        # Load existing data to merge
        existing = {}
        if path.exists():
            try:
                with open(path, "r") as f:
                    existing = json.load(f)
            except Exception:
                pass

        # Update with our data
        for item_name, cast_time_ms in self._item_cast_times.items():
            if item_name in existing:
                cast_times = existing[item_name].get("cast_times_ms", {})
                cast_times[str(cast_time_ms)] = cast_times.get(str(cast_time_ms), 0) + 1
                existing[item_name]["cast_times_ms"] = cast_times
            else:
                existing[item_name] = {"cast_times_ms": {str(cast_time_ms): 1}}

        try:
            with open(path, "w") as f:
                json.dump(existing, f, indent=2)
        except Exception as e:
            print(f"Could not save learned items: {e}")

    def load_history(self) -> None:
        """Load timer history from log."""
        self._loading_history = True
        self._signals.log_message.emit("Loading timer history...")

        hours = self._app_config.timers.history_hours
        entries = self._log_watcher.load_raw_history(hours)

        if not entries:
            self._loading_history = False
            return

        logout_periods = self._log_watcher.find_logout_periods(entries)
        zone_periods = self._log_watcher.find_zone_periods(entries)

        # Process history (simplified - full version would track pending casts)
        active: dict[tuple[str, str], tuple[datetime, any, bool]] = {}
        parser = self._log_watcher.parser

        for entry in entries:
            msg = entry.message

            if parser.is_death(entry):
                active.clear()
                continue

            if fades := self._spell_db.find_by_fades(msg):
                for s in fades:
                    active.pop((s.name, "You"), None)
                continue

            if spells := self._spell_db.find_by_cast_on_you(msg):
                if spell := self._spell_db.best_match(spells):
                    if spell.get_duration_seconds(self._level) > 0:
                        active[(spell.name, "You")] = (entry.timestamp, spell, False)

        # Create timers from history
        loaded = 0
        now = datetime.now()

        for (name, target), (cast_time, spell, is_self) in active.items():
            duration = spell.get_duration_seconds(self._level)

            # Account for logged-out time
            paused = sum(p.time_after(cast_time) for p in logout_periods)
            paused += sum(p.time_after(cast_time) for p in zone_periods)

            wall = (now - cast_time).total_seconds()
            remaining = duration - (wall - paused)

            if remaining > 0:
                category = TimerCategory.SELF_BUFF if is_self else TimerCategory.RECEIVED_BUFF
                timer = ActiveTimer(
                    spell_name=spell.name,
                    target=target,
                    end_time=now + timedelta(seconds=remaining),
                    total_duration=duration,
                    category=category,
                    spell_info=spell,
                )
                self._timer_mgr.add(timer)
                loaded += 1

        self._signals.log_message.emit(f"Loaded {loaded} buffs")
        self._loading_history = False

    def _add_context_menu_items(self, menu: QMenu) -> None:
        """Add timer-specific context menu items."""
        clear_action = menu.addAction("Clear all timers")
        clear_action.triggered.connect(self._timer_mgr.clear)

    def closeEvent(self, event):
        self._update_timer.stop()
        self._combat_timer.stop()
        self._save_learned_items()
        event.accept()
