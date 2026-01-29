"""
Chat panel widgets - conversation list items, message bubbles, etc.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import (
    Qt,
    QTimer,
    pyqtSignal,
    QVariantAnimation,
    QEasingCurve,
    QRectF,
)
from PyQt6.QtGui import (
    QColor,
    QPainter,
    QBrush,
    QPen,
    QFont,
    QFontMetrics,
    QCursor,
    QLinearGradient,
)
from PyQt6.QtWidgets import (
    QFrame,
    QSizePolicy,
    QMenu,
    QApplication,
)

from ..core.data import ChatMessage, Conversation, ChannelType
from ..ui.theme import Theme, get_contrast_text_color, get_contrast_shadow_color, get_luminance, CURATED_PALETTE
from ..ui.widgets.bar import SharedBarStyle
from .conversation_manager import ConversationManager


class ConversationListItem(QFrame):
    """Single item in the conversation list."""

    clicked = pyqtSignal(str)  # Emits conversation ID

    def __init__(self, conversation: Conversation, is_selected: bool = False, parent=None):
        super().__init__(parent)
        self._conversation = conversation
        self._is_selected = is_selected
        self._is_hovered = False
        self._glow_intensity = 0.0
        self._has_unread = conversation.unread_count > 0
        self._pulse_direction = True

        self.setFixedHeight(52)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setMouseTracking(True)

        # Pulsing glow animation for unread
        self._glow_animation = QVariantAnimation(self)
        self._glow_animation.valueChanged.connect(self._on_glow_changed)
        self._glow_animation.finished.connect(self._on_glow_finished)

        if self._has_unread:
            self._start_pulse()

    def _on_glow_changed(self, value):
        self._glow_intensity = value
        self.update()

    def _on_glow_finished(self):
        if self._has_unread:
            self._pulse_direction = not self._pulse_direction
            self._start_pulse()

    def _start_pulse(self):
        self._glow_animation.stop()
        self._glow_animation.setDuration(800)
        if self._pulse_direction:
            self._glow_animation.setStartValue(1.0)
            self._glow_animation.setEndValue(0.4)
        else:
            self._glow_animation.setStartValue(0.4)
            self._glow_animation.setEndValue(1.0)
        self._glow_animation.setEasingCurve(QEasingCurve.Type.InOutSine)
        self._glow_animation.start()

    def flash_glow(self, is_tell: bool = False) -> None:
        self._has_unread = True
        self._pulse_direction = True
        if self._glow_animation.state() != QVariantAnimation.State.Running:
            self._start_pulse()

    def update_conversation(self, conversation: Conversation, is_selected: bool) -> None:
        self._conversation = conversation
        self._is_selected = is_selected

        new_has_unread = conversation.unread_count > 0
        if new_has_unread != self._has_unread:
            self._has_unread = new_has_unread
            if self._has_unread:
                self._start_pulse()
            else:
                self._glow_animation.stop()
                self._glow_intensity = 0.0

        self.update()

    def stop_glow(self) -> None:
        self._has_unread = False
        self._glow_animation.stop()
        self._glow_intensity = 0.0
        self.update()

    def enterEvent(self, event):
        self._is_hovered = True
        self.update()

    def leaveEvent(self, event):
        self._is_hovered = False
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._conversation.id)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        w = self.width()
        h = self.height()
        conv = self._conversation
        color = Theme.get_channel_color(conv.channel.value)

        # Background
        bg_color = QColor(color.red(), color.green(), color.blue(), 50)
        painter.fillRect(0, 0, w, h, bg_color)

        if self._is_selected:
            select_color = QColor(color.red(), color.green(), color.blue(), 80)
            painter.fillRect(0, 0, w, h, select_color)
        elif self._is_hovered:
            painter.fillRect(0, 0, w, h, QColor(255, 255, 255, 25))

        # Color indicator bar
        indicator_width = 5
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(color))
        painter.drawRect(0, 0, indicator_width, h)

        # Glow overlay
        if self._glow_intensity > 0:
            glow_color = QColor(color.red(), color.green(), color.blue(), int(180 * self._glow_intensity))
            painter.fillRect(0, 0, w, h, glow_color)
            painter.setPen(QPen(QColor(255, 255, 255, int(255 * self._glow_intensity)), 3))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(1, 1, w - 2, h - 2)

        # Name
        text_x = indicator_width + 12
        painter.setFont(Theme.font(11, bold=True))
        painter.setPen(QPen(Theme.TEXT_PRIMARY))
        fm = QFontMetrics(painter.font())
        name_width = w - text_x - 10
        if conv.unread_count > 0:
            name_width -= 22
        display_name = fm.elidedText(conv.name, Qt.TextElideMode.ElideRight, name_width)
        painter.drawText(
            text_x, 0, name_width, h,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            display_name
        )

        # Unread badge
        if conv.unread_count > 0:
            badge_size = 18
            badge_x = w - badge_size - 6
            badge_y = (h - badge_size) // 2
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(Theme.UNREAD_BADGE))
            painter.drawEllipse(badge_x, badge_y, badge_size, badge_size)
            painter.setPen(QPen(Theme.TEXT_PRIMARY))
            painter.setFont(Theme.font(8, bold=True))
            painter.drawText(
                badge_x, badge_y, badge_size, badge_size,
                Qt.AlignmentFlag.AlignCenter, str(min(conv.unread_count, 99))
            )

        # Separator
        painter.setPen(QPen(Theme.SEPARATOR))
        painter.drawLine(indicator_width + 8, h - 1, w, h - 1)


class GlobalConversationItem(QFrame):
    """Special conversation list item for the Global combined view."""

    clicked = pyqtSignal(str)
    config_changed = pyqtSignal()

    def __init__(self, conversation: Conversation, is_selected: bool, conv_manager: ConversationManager, parent=None):
        super().__init__(parent)
        self._conversation = conversation
        self._conv_manager = conv_manager
        self._is_selected = is_selected
        self._is_hovered = False

        self.setFixedHeight(52)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setMouseTracking(True)

    def update_conversation(self, conversation: Conversation, is_selected: bool) -> None:
        self._conversation = conversation
        self._is_selected = is_selected
        self.update()

    def enterEvent(self, event):
        self._is_hovered = True
        self.update()

    def leaveEvent(self, event):
        self._is_hovered = False
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(ConversationManager.GLOBAL_ID)
        elif event.button() == Qt.MouseButton.RightButton:
            self._show_config_menu(event.globalPosition().toPoint())

    def _show_config_menu(self, pos) -> None:
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: rgba(35, 35, 50, 250);
                border: 1px solid rgba(80, 80, 100, 200);
                padding: 4px;
            }
            QMenu::item { color: white; padding: 6px 20px; }
            QMenu::item:selected { background-color: rgba(70, 70, 100, 200); }
            QMenu::indicator { width: 14px; height: 14px; }
            QMenu::indicator:checked {
                background-color: rgba(100, 150, 255, 200);
                border-radius: 3px;
            }
        """)

        channels = [
            ("guild", "Guild"),
            ("ooc", "OOC"),
            ("group", "Group"),
            ("shout", "Shout"),
            ("auction", "Auction"),
            ("random", "Random"),
            ("tell", "Tells"),
        ]

        selected_channels = self._conv_manager.get_global_channels()

        for channel_id, channel_name in channels:
            action = menu.addAction(channel_name)
            action.setCheckable(True)
            action.setChecked(channel_id in selected_channels)
            action.triggered.connect(lambda checked, cid=channel_id: self._toggle_channel(cid))

        menu.exec(pos)

    def _toggle_channel(self, channel_id: str) -> None:
        self._conv_manager.toggle_global_channel(channel_id)
        self.config_changed.emit()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        w = self.width()
        h = self.height()

        # Gradient background
        gradient = QLinearGradient(0, 0, w, 0)
        gradient.setColorAt(0.0, QColor(76, 140, 92, 50))
        gradient.setColorAt(0.5, QColor(128, 90, 160, 50))
        gradient.setColorAt(1.0, QColor(85, 120, 180, 50))
        painter.fillRect(0, 0, w, h, gradient)

        if self._is_selected:
            painter.fillRect(0, 0, w, h, QColor(255, 255, 255, 50))
        elif self._is_hovered:
            painter.fillRect(0, 0, w, h, QColor(255, 255, 255, 25))

        # Multi-color bar
        bar_width = 5
        bar_gradient = QLinearGradient(0, 0, 0, h)
        bar_gradient.setColorAt(0.0, CURATED_PALETTE["green"][0])
        bar_gradient.setColorAt(0.33, CURATED_PALETTE["purple"][0])
        bar_gradient.setColorAt(0.66, CURATED_PALETTE["blue"][0])
        bar_gradient.setColorAt(1.0, CURATED_PALETTE["gold"][0])
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(bar_gradient))
        painter.drawRect(0, 0, bar_width, h)

        # Name
        text_x = bar_width + 12
        painter.setFont(Theme.font(11, bold=True))
        painter.setPen(QPen(Theme.TEXT_PRIMARY))
        painter.drawText(
            text_x, 0, w - text_x - 10, h,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            "🌐 Global"
        )

        # Channel count
        channel_count = len(self._conv_manager.get_global_channels())
        hint_text = f"({channel_count})"
        painter.setFont(Theme.font(9))
        painter.setPen(QPen(Theme.TEXT_DIM))
        fm = QFontMetrics(painter.font())
        hint_width = fm.horizontalAdvance(hint_text)
        painter.drawText(
            w - hint_width - 10, 0, hint_width, h,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
            hint_text
        )

        # Separator
        painter.setPen(QPen(Theme.SEPARATOR))
        painter.drawLine(bar_width + 8, h - 1, w, h - 1)


class MessageBubble(QFrame):
    """Single message bubble in conversation view."""

    def __init__(self, message: ChatMessage, show_sender: bool = True, max_width: int = 200, parent=None):
        super().__init__(parent)
        self._message = message
        self._show_sender = show_sender
        self._max_bubble_width = max_width
        self._flash_intensity = 0.0

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self._calculate_height()

        # Flash animation
        self._flash_animation = QVariantAnimation(self)
        self._flash_animation.setDuration(600)
        self._flash_animation.setStartValue(0.5)
        self._flash_animation.setEndValue(0.0)
        self._flash_animation.setEasingCurve(QEasingCurve.Type.OutQuad)
        self._flash_animation.valueChanged.connect(self._on_flash_changed)

    def _on_flash_changed(self, value):
        self._flash_intensity = value
        self.update()

    def flash(self) -> None:
        self._flash_animation.start()

    def _show_context_menu(self, pos) -> None:
        """Show right-click context menu."""
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: rgba(40, 40, 50, 0.95);
                border: 1px solid rgba(100, 100, 120, 0.5);
                border-radius: 4px;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 20px;
                color: white;
            }
            QMenu::item:selected {
                background-color: rgba(80, 80, 100, 0.8);
            }
        """)
        
        copy_action = menu.addAction("Copy Message")
        copy_action.triggered.connect(self._copy_message)
        
        copy_with_sender = menu.addAction("Copy with Sender")
        copy_with_sender.triggered.connect(self._copy_with_sender)
        
        copy_raw = menu.addAction("Copy Raw (with timestamps)")
        copy_raw.triggered.connect(self._copy_raw)
        
        menu.exec(self.mapToGlobal(pos))

    def _copy_message(self) -> None:
        """Copy message content to clipboard."""
        clipboard = QApplication.clipboard()
        clipboard.setText(self._message.content)

    def _copy_with_sender(self) -> None:
        """Copy message with sender info to clipboard."""
        clipboard = QApplication.clipboard()
        text = f"[{self._message.display_time}] {self._message.sender}: {self._message.content}"
        clipboard.setText(text)

    def _copy_raw(self) -> None:
        """Copy raw log format with full timestamps."""
        clipboard = QApplication.clipboard()
        # Format timestamp like EQ log: [Tue Jan 27 17:33:07 2026]
        ts = self._message.timestamp.strftime("%a %b %d %H:%M:%S %Y")
        
        # For multi-line content (like /who), add timestamp to each line
        lines = self._message.content.split('\n')
        if len(lines) > 1:
            raw_lines = [f"[{ts}] {line}" for line in lines]
            text = '\n'.join(raw_lines)
        else:
            text = f"[{ts}] {self._message.content}"
        
        clipboard.setText(text)

    def _calculate_height(self) -> None:
        font = Theme.font(11)
        fm = QFontMetrics(font)

        text_width = self._max_bubble_width - 24
        rect = fm.boundingRect(
            0, 0, text_width, 10000,
            Qt.TextFlag.TextWordWrap, self._message.content
        )

        header_height = 22 if self._show_sender else 0
        content_height = rect.height() + 18
        self.setFixedHeight(header_height + content_height + 8)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        w = self.width()
        h = self.height()
        msg = self._message

        # Special handling for winner announcement (System messages with 🏆)
        is_winner_msg = msg.sender == "System" and msg.content.startswith("🏆")
        is_separator_msg = msg.sender == "System" and msg.content.startswith("──")
        is_dq_msg = msg.sender == "System" and msg.content.startswith("⛔")
        
        if is_winner_msg:
            bubble_color = QColor(218, 165, 32)  # Gold color
        elif is_separator_msg:
            bubble_color = QColor(80, 80, 100)  # Gray for separator
        elif is_dq_msg:
            bubble_color = QColor(180, 60, 60)  # Red for DQ
        else:
            bubble_color = Theme.get_channel_color(msg.channel.value)
        is_outgoing = msg.is_outgoing

        font = Theme.font(11)
        fm = QFontMetrics(font)

        text_width = self._max_bubble_width - 24
        text_rect = fm.boundingRect(
            0, 0, text_width, 10000,
            Qt.TextFlag.TextWordWrap, msg.content
        )

        bubble_width = min(self._max_bubble_width, max(100, text_rect.width() + 28))
        bubble_height = h - (24 if self._show_sender else 8)

        margin = 6
        radius = 10

        # Center winner/separator/DQ messages, otherwise left/right based on outgoing
        if is_winner_msg or is_separator_msg or is_dq_msg:
            bubble_x = (w - bubble_width) // 2
        elif is_outgoing:
            bubble_x = w - bubble_width - margin
        else:
            bubble_x = margin

        bubble_y = 22 if self._show_sender else 4

        # Header
        if self._show_sender:
            painter.setFont(Theme.font(10, bold=True))
            
            # For outgoing tells, show "To <recipient>" instead of sender
            if is_outgoing and msg.channel == ChannelType.TELL and msg.tell_target:
                header_text = f"To {msg.tell_target.capitalize()} · {msg.display_time}"
            else:
                header_text = f"{msg.sender.capitalize()} · {msg.display_time}"

            painter.setPen(QPen(Theme.TEXT_SHADOW))
            if is_outgoing:
                painter.drawText(
                    margin, 0, w - margin * 2, 18,
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                    header_text
                )
            else:
                painter.drawText(
                    margin + 1, 1, w - margin * 2, 18,
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                    header_text
                )

            painter.setPen(QPen(Theme.TEXT_DIM))
            if is_outgoing:
                painter.drawText(
                    margin, 0, w - margin * 2, 18,
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                    header_text
                )
            else:
                painter.drawText(
                    margin, 0, w - margin * 2, 18,
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                    header_text
                )

        # Bubble background with shared styling
        bubble_rect = QRectF(bubble_x, bubble_y, bubble_width, bubble_height)
        SharedBarStyle.draw_bubble(painter, bubble_rect, bubble_color, radius)

        # Text
        painter.setFont(font)
        text_x = bubble_x + 12
        text_y = bubble_y + 8
        text_h = bubble_height - 16

        text_rect = QRectF(text_x, text_y, text_width, text_h)

        text_color = get_contrast_text_color(bubble_color)
        shadow_color = get_contrast_shadow_color(bubble_color)

        # Shadow
        shadow_rect = QRectF(text_x + 1, text_y + 1, text_width, text_h)
        painter.setPen(QPen(shadow_color))
        painter.drawText(shadow_rect, Qt.TextFlag.TextWordWrap, msg.content)

        # Main text
        painter.setPen(QPen(text_color))
        painter.drawText(text_rect, Qt.TextFlag.TextWordWrap, msg.content)

        # Flash overlay
        if self._flash_intensity > 0:
            painter.setPen(Qt.PenStyle.NoPen)
            if get_luminance(bubble_color) > 0.5:
                flash_color = QColor(0, 0, 0, int(80 * self._flash_intensity))
            else:
                flash_color = QColor(255, 255, 255, int(100 * self._flash_intensity))
            painter.setBrush(QBrush(flash_color))
            painter.drawRoundedRect(bubble_rect, radius, radius)
