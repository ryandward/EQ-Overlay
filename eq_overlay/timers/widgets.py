"""
Timer panel widgets - using shared bar styling.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, QRectF, QPointF, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen, QBrush, QFont, QFontMetrics
from PyQt6.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy, QWidget, QToolTip

from ..core.data import ActiveTimer, TimerCategory
from ..core.duration import format_duration
from ..ui.theme import Theme
from ..ui.widgets.bar import SharedBarStyle, BaseBarWidget


class CircularTimerWidget(QFrame):
    """
    Circular timer that depletes like a clock.
    Used for showing buffs on others compactly.
    """
    
    SIZE = 52  # Diameter of the circle
    
    clicked = pyqtSignal(object)  # Emits the timer
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(self.SIZE, self.SIZE)
        self._timer: Optional[ActiveTimer] = None
        self.setMouseTracking(True)
        self.setToolTipDuration(5000)
        self.setStyleSheet("background: transparent;")
    
    @staticmethod
    def _get_initials(spell_name: str) -> str:
        """Get smart initials: first letter of up to 3 words, or first 3 letters if single word."""
        words = spell_name.split()
        if len(words) >= 3:
            # 3+ words: first letter of first three words
            return (words[0][0] + words[1][0] + words[2][0]).upper()
        elif len(words) == 2:
            # Two words: first letter of each
            return (words[0][0] + words[1][0]).upper()
        else:
            # Single word: first two letters
            return spell_name[:2].upper()
    
    def set_timer(self, timer: Optional[ActiveTimer]) -> None:
        self._timer = timer
        if timer:
            remaining = format_duration(timer.remaining_seconds)
            self.setToolTip(f"{timer.spell_name}\n{remaining} remaining")
        else:
            self.setToolTip("")
        self.update()
    
    def paintEvent(self, event):
        if not self._timer:
            return
            
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        timer = self._timer
        percent = timer.percent_remaining
        
        # Get color by category
        color = {
            TimerCategory.SELF_BUFF: Theme.TIMER_SELF_BUFF,
            TimerCategory.RECEIVED_BUFF: Theme.TIMER_RECEIVED_BUFF,
            TimerCategory.DEBUFF: Theme.TIMER_DEBUFF,
            TimerCategory.OTHER_BUFF: Theme.TIMER_OTHER_BUFF,
        }.get(timer.category, Theme.TIMER_OTHER_BUFF)
        
        margin = 2
        size = self.SIZE - margin * 2
        rect = QRectF(margin, margin, size, size)
        
        # Background circle (dark)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(SharedBarStyle.BG_FILLED))
        painter.drawEllipse(rect)
        
        # Progress arc - draws clockwise from 12 o'clock
        # Qt uses 1/16th of a degree, 0 = 3 o'clock, so we start at 90° (12 o'clock)
        # and sweep negative (clockwise)
        if percent > 0:
            start_angle = 90 * 16  # 12 o'clock in Qt units
            span_angle = -int((percent / 100.0) * 360 * 16)  # Negative = clockwise
            
            painter.setBrush(QBrush(color))
            painter.drawPie(rect, start_angle, span_angle)
            
            # Shine overlay on the filled part
            shine_color = QColor(255, 255, 255, 40)
            painter.setBrush(QBrush(shine_color))
            painter.drawPie(rect.adjusted(0, 0, 0, -size/2), start_angle, span_angle)
        
        # Border
        painter.setPen(QPen(SharedBarStyle.BORDER_COLOR, 1.5))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(rect)
        
        # Spell initials in center
        painter.setFont(Theme.font_lg(bold=True))
        initials = self._get_initials(timer.spell_name)
        painter.setPen(QPen(Theme.TEXT_PRIMARY))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, initials)
    
    def enterEvent(self, event):
        # Show tooltip on hover
        if self._timer:
            remaining = format_duration(self._timer.remaining_seconds)
            QToolTip.showText(
                self.mapToGlobal(QPointF(self.width() // 2, self.height())).toPoint(),
                f"{self._timer.spell_name}\n{remaining} remaining",
                self
            )
    
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._timer:
            self.clicked.emit(self._timer)


class TargetBuffsRow(QFrame):
    """
    DEPRECATED - kept for reference. Use SpellGroupWidget instead.
    A row showing all buffs on a single target as circular timers.
    """
    
    MAX_CIRCLES = 6  # Max circles before we'd need to scroll/wrap
    
    def __init__(self, target_name: str, parent=None):
        super().__init__(parent)
        self._target_name = target_name
        self._timers: list[ActiveTimer] = []
        self._circles: list[CircularTimerWidget] = []
        
        self.setStyleSheet("background: rgba(40, 40, 60, 100); border-radius: 4px;")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)
        
        # Target name label
        self._name_label = QLabel(target_name)
        self._name_label.setStyleSheet(f"""
            color: rgba(200, 200, 220, 230);
            {Theme.css_font_xl()}
        """)
        self._name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._name_label)
        
        # Container for circles
        circles_container = QWidget()
        circles_container.setStyleSheet("background: transparent;")
        self._circles_layout = QHBoxLayout(circles_container)
        self._circles_layout.setContentsMargins(4, 0, 4, 0)
        self._circles_layout.setSpacing(6)
        self._circles_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Pre-create circle widgets
        for _ in range(self.MAX_CIRCLES):
            circle = CircularTimerWidget()
            circle.hide()
            self._circles.append(circle)
            self._circles_layout.addWidget(circle)
        
        layout.addWidget(circles_container)
        
        self._update_height()
    
    def _update_height(self):
        # Name label (~22px) + circles (~56px) + margins
        self.setFixedHeight(82)
    
    def update_timers(self, timers: list[ActiveTimer]) -> None:
        """Update the timers shown for this target."""
        self._timers = timers
        
        # Sort by time remaining
        sorted_timers = sorted(timers, key=lambda t: t.remaining_seconds)
        
        for i, circle in enumerate(self._circles):
            if i < len(sorted_timers):
                circle.set_timer(sorted_timers[i])
                circle.show()
            else:
                circle.set_timer(None)
                circle.hide()
    
    @property
    def target_name(self) -> str:
        return self._target_name


class SpellTargetRow(QFrame):
    """
    A single row showing target name and time remaining for a spell.
    Glows increasingly as time runs out (warning at 2 min, urgent at 20 sec).
    """
    
    ROW_HEIGHT = 20
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._timer: Optional[ActiveTimer] = None
        self.setFixedHeight(self.ROW_HEIGHT)
        self.setStyleSheet("background: transparent;")
    
    def set_timer(self, timer: Optional[ActiveTimer]) -> None:
        self._timer = timer
        self.update()
    
    def _get_glow_intensity(self, remaining_seconds: float) -> float:
        """Calculate glow intensity based on time remaining."""
        import math
        
        warning = Theme.TIMER_WARNING_THRESHOLD
        urgent = Theme.TIMER_URGENT_THRESHOLD
        
        if remaining_seconds > warning:
            return 0.0
        
        if remaining_seconds <= urgent:
            # Pulsing between 0.5 and 1.0, faster as time decreases
            pulse = (math.sin(remaining_seconds * 3.14159) + 1) / 2  # 0 to 1
            return 0.5 + pulse * 0.5
        
        # Linear ramp from 0 to 0.5 between warning and urgent thresholds
        progress = (warning - remaining_seconds) / (warning - urgent)
        return progress * 0.5
    
    def paintEvent(self, event):
        if not self._timer:
            return
        
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        
        timer = self._timer
        w = self.width()
        h = self.height()
        
        # Get color from theme (DRY)
        base_color = {
            TimerCategory.SELF_BUFF: Theme.TIMER_SELF_BUFF,
            TimerCategory.RECEIVED_BUFF: Theme.TIMER_RECEIVED_BUFF,
            TimerCategory.DEBUFF: Theme.TIMER_DEBUFF,
            TimerCategory.OTHER_BUFF: Theme.TIMER_OTHER_BUFF,
        }.get(timer.category, Theme.TIMER_OTHER_BUFF)
        
        # Draw glow background if warning
        glow_intensity = self._get_glow_intensity(timer.remaining_seconds)
        if glow_intensity > 0:
            glow_color = QColor(base_color)
            glow_color.setAlphaF(glow_intensity * 0.4)  # Max 40% opacity
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(glow_color))
            painter.drawRoundedRect(QRectF(0, 0, w, h), 3, 3)
        
        # Mini progress bar on the left
        bar_width = 4
        bar_height = h - 6
        bar_x = 4
        bar_y = 3
        
        # Bar background
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(40, 40, 50, 150)))
        painter.drawRoundedRect(QRectF(bar_x, bar_y, bar_width, bar_height), 2, 2)
        
        # Bar fill (from bottom)
        percent = timer.percent_remaining / 100.0
        fill_height = bar_height * percent
        fill_y = bar_y + (bar_height - fill_height)
        painter.setBrush(QBrush(base_color))
        painter.drawRoundedRect(QRectF(bar_x, fill_y, bar_width, fill_height), 2, 2)
        
        # Target name
        text_x = bar_x + bar_width + 8
        painter.setFont(Theme.font_sm())
        painter.setPen(QPen(Theme.TEXT_PRIMARY))
        painter.drawText(
            int(text_x), 0, int(w - text_x - 50), h,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            timer.target
        )
        
        # Time remaining on right (consistent color, glow handles urgency)
        time_str = format_duration(timer.remaining_seconds)
        painter.setFont(Theme.font_sm(bold=True))
        painter.setPen(QPen(Theme.TEXT_DIM))
        painter.drawText(
            0, 0, w - 8, h,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            time_str
        )


class SpellGroupWidget(QFrame):
    """
    A group showing one spell with all targets who have it.
    Grouped by spell, sorted by time remaining (soonest first).
    
    Layout:
    ┌─────────────────────────────────────────┐
    │ Clarity II ─────────────────────────────│
    │ │ Soandso                         12:34 │
    │ │ Otherguy                        11:22 │
    └─────────────────────────────────────────┘
    """
    
    MAX_TARGETS = 12  # Max targets to show per spell
    HEADER_HEIGHT = 22
    
    def __init__(self, spell_name: str, parent=None):
        super().__init__(parent)
        self._spell_name = spell_name
        self._timers: list[ActiveTimer] = []
        self._target_rows: list[SpellTargetRow] = []
        
        self.setStyleSheet("background: rgba(40, 40, 60, 80); border-radius: 4px;")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(2)
        
        # Spell name header
        self._header = QLabel(spell_name)
        self._header.setFixedHeight(self.HEADER_HEIGHT)
        self._header.setStyleSheet(f"""
            color: rgba(180, 180, 200, 255);
            {Theme.css_font_sm(bold=True)}
            border-bottom: 1px solid rgba(100, 100, 120, 100);
            padding-bottom: 2px;
        """)
        layout.addWidget(self._header)
        
        # Container for target rows
        self._rows_container = QWidget()
        self._rows_container.setStyleSheet("background: transparent;")
        self._rows_layout = QVBoxLayout(self._rows_container)
        self._rows_layout.setContentsMargins(0, 2, 0, 0)
        self._rows_layout.setSpacing(1)
        
        # Pre-create target rows
        for _ in range(self.MAX_TARGETS):
            row = SpellTargetRow()
            row.hide()
            self._target_rows.append(row)
            self._rows_layout.addWidget(row)
        
        layout.addWidget(self._rows_container)
        self._update_height(0)
    
    def _update_height(self, num_targets: int):
        # Header + rows
        height = self.HEADER_HEIGHT + 8  # header + margins
        height += max(1, num_targets) * (SpellTargetRow.ROW_HEIGHT + 1)  # rows + spacing
        self.setFixedHeight(height)
    
    def update_timers(self, timers: list[ActiveTimer]) -> None:
        """Update the timers for this spell group."""
        self._timers = timers
        
        # Sort by time remaining (soonest first - needs rebuff soon)
        sorted_timers = sorted(timers, key=lambda t: t.remaining_seconds)
        
        for i, row in enumerate(self._target_rows):
            if i < len(sorted_timers):
                row.set_timer(sorted_timers[i])
                row.show()
            else:
                row.set_timer(None)
                row.hide()
        
        self._update_height(len(sorted_timers))
    
    @property
    def spell_name(self) -> str:
        return self._spell_name


class TimerBarWidget(BaseBarWidget):
    """Single timer bar widget with warning glow."""

    def __init__(self, parent=None):
        super().__init__(SharedBarStyle.BAR_HEIGHT, parent)
        self._timer: Optional[ActiveTimer] = None

    def set_timer(self, timer: Optional[ActiveTimer]) -> None:
        self._timer = timer
        self.update()
    
    def _get_glow_intensity(self, remaining_seconds: float) -> float:
        """Calculate glow intensity based on time remaining."""
        import math
        
        warning = Theme.TIMER_WARNING_THRESHOLD
        urgent = Theme.TIMER_URGENT_THRESHOLD
        
        if remaining_seconds > warning:
            return 0.0
        
        if remaining_seconds <= urgent:
            # Pulsing between 0.5 and 1.0
            pulse = (math.sin(remaining_seconds * 3.14159) + 1) / 2
            return 0.5 + pulse * 0.5
        
        # Linear ramp from 0 to 0.5 between warning and urgent thresholds
        progress = (warning - remaining_seconds) / (warning - urgent)
        return progress * 0.5

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.get_bar_rect()

        # Background
        SharedBarStyle.draw_bar_background(painter, rect)

        if not self._timer:
            return

        timer = self._timer
        percent = timer.percent_remaining

        # Get color by category
        color = {
            TimerCategory.SELF_BUFF: Theme.TIMER_SELF_BUFF,
            TimerCategory.RECEIVED_BUFF: Theme.TIMER_RECEIVED_BUFF,
            TimerCategory.DEBUFF: Theme.TIMER_DEBUFF,
            TimerCategory.OTHER_BUFF: Theme.TIMER_OTHER_BUFF,
        }.get(timer.category, Theme.TIMER_OTHER_BUFF)

        # Draw glow if warning
        glow_intensity = self._get_glow_intensity(timer.remaining_seconds)
        if glow_intensity > 0:
            glow_color = QColor(color)
            glow_color.setAlphaF(glow_intensity * 0.3)  # Max 30% opacity
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(glow_color))
            # Draw glow slightly larger than the bar
            glow_rect = QRectF(rect.x() - 2, rect.y() - 2, rect.width() + 4, rect.height() + 4)
            painter.drawRoundedRect(glow_rect, SharedBarStyle.BAR_RADIUS + 2, SharedBarStyle.BAR_RADIUS + 2)

        # Progress fill
        SharedBarStyle.draw_bar_progress(painter, rect, percent, color)

        # Border
        SharedBarStyle.draw_bar_border(painter, rect)

        # Text
        painter.setFont(Theme.font(9, bold=True))
        text_rect = QRectF(rect.x() + 8, rect.y(), rect.width() - 16, rect.height())

        # Spell name (left)
        name = timer.spell_name[:22]
        SharedBarStyle.draw_shadowed_text(
            painter, text_rect, name,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )

        # Time remaining (right)
        time_str = format_duration(timer.remaining_seconds)
        SharedBarStyle.draw_shadowed_text(
            painter, text_rect, time_str,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )


class CastingBarWidget(BaseBarWidget):
    """Casting progress bar."""

    CASTING_COLOR = QColor(100, 180, 220)

    def __init__(self, parent=None):
        super().__init__(32, parent)
        self._spell_name: Optional[str] = None
        self._elapsed_ms: float = 0
        self._total_ms: float = 0

    def set_casting(self, spell_name: Optional[str], elapsed_ms: float, total_ms: float) -> None:
        self._spell_name = spell_name
        self._elapsed_ms = elapsed_ms
        self._total_ms = total_ms
        self.update()

    def clear(self) -> None:
        self._spell_name = None
        self.update()

    def paintEvent(self, event):
        if not self._spell_name or self._total_ms <= 0:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.get_bar_rect()

        # Background
        SharedBarStyle.draw_bar_background(painter, rect)

        # Progress - shows REMAINING time (drains as cast progresses)
        remaining_ms = max(0, self._total_ms - self._elapsed_ms)
        percent = min(100, (remaining_ms / self._total_ms) * 100)
        SharedBarStyle.draw_bar_progress(painter, rect, percent, self.CASTING_COLOR)

        # Border
        SharedBarStyle.draw_bar_border(painter, rect)

        # Text
        painter.setFont(Theme.font_sm(bold=True))
        text = f"🎯 {self._spell_name} ({remaining_ms / 1000:.1f}s)"

        text_rect = QRectF(rect.x() + 8, rect.y(), rect.width() - 16, rect.height())
        SharedBarStyle.draw_shadowed_text(
            painter, text_rect, text,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )


class DPSBarWidget(BaseBarWidget):
    """Single DPS bar widget."""

    def __init__(self, parent=None):
        super().__init__(SharedBarStyle.BAR_HEIGHT, parent)
        self._player_name = ""
        self._damage = 0
        self._dps = 0.0
        self._percent = 0.0
        self._is_you = False

    def set_data(self, player_name: str, damage: int, dps: float, percent: float, is_you: bool) -> None:
        self._player_name = player_name
        self._damage = damage
        self._dps = dps
        self._percent = percent
        self._is_you = is_you
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.get_bar_rect()

        # Background
        SharedBarStyle.draw_bar_background(painter, rect)

        if not self._player_name:
            return

        # Progress
        color = Theme.DPS_YOU if self._is_you else Theme.DPS_OTHER
        SharedBarStyle.draw_bar_progress(painter, rect, self._percent, color)

        # Border
        SharedBarStyle.draw_bar_border(painter, rect)

        # Text
        painter.setFont(Theme.font(9, bold=True))
        text_rect = QRectF(rect.x() + 8, rect.y(), rect.width() - 16, rect.height())

        # Player name (left) - highlight if you
        name_color = QColor(255, 200, 200) if self._is_you else Theme.TEXT_PRIMARY
        display_name = self._player_name[:12]
        left_rect = QRectF(rect.x() + 8, rect.y(), rect.width() / 3, rect.height())
        SharedBarStyle.draw_shadowed_text(
            painter, left_rect, display_name,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            name_color
        )

        # DPS (center)
        center_rect = QRectF(rect.x() + rect.width() / 3, rect.y(), rect.width() / 3, rect.height())
        SharedBarStyle.draw_shadowed_text(
            painter, center_rect, f"{self._dps:.1f}",
            Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter
        )

        # Damage (right)
        right_rect = QRectF(rect.x() + 8, rect.y(), rect.width() - 16, rect.height())
        SharedBarStyle.draw_shadowed_text(
            painter, right_rect, f"{self._damage:,}",
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )


class DPSMeterWidget(QFrame):
    """DPS meter showing you + top players."""

    MAX_PLAYERS = 6

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setStyleSheet("background: transparent;")
        self.setFixedHeight(24 + (self.MAX_PLAYERS * 32))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._header = QLabel("⚔ DPS Meter")
        self._header.setStyleSheet(f"""
            color: rgba(180, 180, 200, 200);
            {Theme.css_font_sm()}
            padding: 2px 8px;
        """)
        layout.addWidget(self._header)

        self._bars: list[DPSBarWidget] = []
        for _ in range(self.MAX_PLAYERS):
            bar = DPSBarWidget()
            self._bars.append(bar)
            layout.addWidget(bar)

        self._active = False

    def update_dps(self, data: dict) -> None:
        self._active = data.get("active", False)
        ended = data.get("ended", False)
        players = data.get("players", [])
        duration = data.get("duration", 0)
        target = data.get("target", "")

        if players:
            if ended:
                self._header.setText(f"☠ {target[:20]} - {duration:.1f}s")
                self._header.setStyleSheet(f"""
                    color: rgba(150, 150, 150, 200);
                    {Theme.css_font_sm()} padding: 2px 8px;
                """)
            else:
                self._header.setText(f"⚔ {target[:20]} ({duration:.1f}s)")
                self._header.setStyleSheet(f"""
                    color: rgba(180, 180, 200, 200);
                    {Theme.css_font_sm()} padding: 2px 8px;
                """)

            max_damage = players[0]["damage"] if players else 1

            you_data = None
            others = []
            for p in players:
                if p["name"] == "You":
                    you_data = p
                else:
                    others.append(p)

            ordered = []
            if you_data:
                ordered.append(you_data)
            ordered.extend(others[: self.MAX_PLAYERS - (1 if you_data else 0)])

            for i, bar in enumerate(self._bars):
                if i < len(ordered):
                    p = ordered[i]
                    percent = (p["damage"] / max_damage) * 100 if max_damage > 0 else 0
                    bar.set_data(p["name"], p["damage"], p["dps"], percent, p["name"] == "You")
                else:
                    bar.set_data("", 0, 0.0, 0.0, False)
        else:
            for bar in self._bars:
                bar.set_data("", 0, 0.0, 0.0, False)
