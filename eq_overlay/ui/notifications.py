"""
Shared Notification Center - displays toast-style notifications from all sources.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import (
    Qt,
    QTimer,
    QPropertyAnimation,
    QEasingCurve,
    pyqtSignal,
    pyqtProperty,
    QRectF,
)
from PyQt6.QtGui import (
    QColor,
    QPainter,
    QBrush,
    QPen,
    QFont,
    QCursor,
    QRegion,
)
from PyQt6.QtWidgets import (
    QWidget,
    QApplication,
    QGraphicsOpacityEffect,
)

from ..core.data import Notification, NotificationType, ChannelType
from ..core.eq_utils import play_notification_sound
from ..config import NotificationsConfig
from .theme import Theme
from .widgets.bar import SharedBarStyle


class NotificationBubble(QWidget):
    """A single notification bubble."""

    clicked = pyqtSignal(object)  # Emits the Notification when clicked
    dismissed = pyqtSignal(object)  # Emits self when animation done

    def __init__(self, notification: Notification, config: NotificationsConfig, parent=None):
        super().__init__(parent)
        self._notification = notification
        self._config = config
        self._y_offset = 0

        self.setFixedSize(config.width, 100)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        # Opacity effect for fade out
        self._opacity_effect = QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(1.0)
        self.setGraphicsEffect(self._opacity_effect)

        # Slide-in animation
        self._slide_anim = QPropertyAnimation(self, b"yOffset")
        self._slide_anim.setDuration(200)
        self._slide_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        # Fade-out animation
        self._fade_anim = QPropertyAnimation(self._opacity_effect, b"opacity")
        self._fade_anim.setDuration(300)
        self._fade_anim.setStartValue(1.0)
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.InCubic)
        self._fade_anim.finished.connect(lambda: self.dismissed.emit(self))

        # Auto-dismiss timer
        self._dismiss_timer = QTimer(self)
        self._dismiss_timer.setSingleShot(True)
        self._dismiss_timer.timeout.connect(self.fade_out)

    def start_dismiss_timer(self, ms: int) -> None:
        """Start the auto-dismiss timer."""
        self._dismiss_timer.start(ms)

    def _get_y_offset(self) -> int:
        return self._y_offset

    def _set_y_offset(self, value: int) -> None:
        self._y_offset = value
        self.update()
        # Notify parent to update mask
        if self.parent():
            self.parent().update_mask()

    yOffset = pyqtProperty(int, _get_y_offset, _set_y_offset)

    def slide_in(self, start_y: int = -100) -> None:
        """Animate sliding in from above."""
        self._slide_anim.setStartValue(start_y)
        self._slide_anim.setEndValue(0)
        self._slide_anim.start()

    def fade_out(self) -> None:
        """Start fade out animation."""
        self._dismiss_timer.stop()
        self._fade_anim.start()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._notification)
            self.fade_out()

    def _get_accent_color(self) -> QColor:
        """Get accent color based on notification type."""
        notif = self._notification

        if notif.channel:
            return Theme.get_channel_color(notif.channel.value)

        type_colors = {
            NotificationType.CHAT_TELL: Theme.CHANNEL_TELL,
            NotificationType.CHAT_MESSAGE: Theme.CHANNEL_GUILD,
            NotificationType.BUFF_WARNING: Theme.PAUSED,
            NotificationType.BUFF_FADED: Theme.TIMER_DEBUFF,
            NotificationType.COMBAT_END: Theme.DPS_YOU,
            NotificationType.SYSTEM: Theme.TEXT_DIM,
        }
        return type_colors.get(notif.type, Theme.TEXT_PRIMARY)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        w = self.width()
        h = self.height()
        notif = self._notification
        accent = self._get_accent_color()

        # Background with shared bubble styling
        bg_rect = QRectF(0, 0, w, h)
        SharedBarStyle.draw_bubble(painter, bg_rect, Theme.NOTIFICATION_BG, 12)

        # Accent bar on left
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(accent))
        painter.drawRoundedRect(QRectF(0, 0, 5, h), 2, 2)

        # Icon + Title
        painter.setFont(Theme.font_sm(bold=True))

        icon = notif.icon or self._get_default_icon()
        title = f"{icon} {notif.title}"

        painter.setPen(QPen(accent))
        painter.drawText(
            15, 8, w - 30, 24,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            title
        )

        # Message content (word wrapped)
        painter.setFont(Theme.font_md())
        painter.setPen(QPen(Theme.TEXT_PRIMARY))
        text_rect = QRectF(15, 34, w - 30, h - 42)
        painter.drawText(text_rect, Qt.TextFlag.TextWordWrap, notif.message)

    def _get_default_icon(self) -> str:
        """Get default icon for notification type."""
        icons = {
            NotificationType.CHAT_TELL: "💬",
            NotificationType.CHAT_MESSAGE: "📢",
            NotificationType.BUFF_WARNING: "⚠️",
            NotificationType.BUFF_FADED: "💨",
            NotificationType.COMBAT_END: "☠️",
            NotificationType.SYSTEM: "ℹ️",
        }
        return icons.get(self._notification.type, "📌")


class NotificationCenter(QWidget):
    """
    Shared notification overlay - receives notifications from all sources
    and displays them in a consistent way.
    """

    bubble_clicked = pyqtSignal(object)  # Notification

    TOP_MARGIN = 20

    def __init__(self, config: NotificationsConfig):
        super().__init__()
        self._config = config
        self._bubbles: list[NotificationBubble] = []

        # Frameless, transparent, always on top, no taskbar, no focus
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setWindowTitle("EQ Overlay Notifications")

        self._position_on_screen()
        self.update_mask()

    def _position_on_screen(self) -> None:
        """Position based on config (top_center, top_left, top_right)."""
        screen = QApplication.primaryScreen()
        if not screen:
            return

        screen_geo = screen.availableGeometry()
        width = self._config.width + 40
        height = (100 + self._config.spacing) * self._config.max_visible + self.TOP_MARGIN * 2

        if self._config.position == "top_left":
            x = screen_geo.x() + 20
        elif self._config.position == "top_right":
            x = screen_geo.x() + screen_geo.width() - width - 20
        else:  # top_center (default)
            x = screen_geo.x() + (screen_geo.width() - width) // 2

        y = screen_geo.y()
        self.setGeometry(x, y, width, height)

    def update_mask(self) -> None:
        """Update the click mask to only include bubble areas."""
        if not self._bubbles:
            # No bubbles - hide the window entirely so it doesn't block clicks
            self.hide()
            return
        
        # Make sure we're visible when we have bubbles
        if not self.isVisible():
            self.show()

        mask = QRegion()
        for bubble in self._bubbles:
            if bubble.isVisible():
                rect = bubble.geometry()
                mask = mask.united(QRegion(rect))

        if mask.isEmpty():
            self.hide()
        else:
            self.setMask(mask)

    def show_notification(self, notification: Notification) -> None:
        """Show a new notification."""
        # Remove oldest if at max
        while len(self._bubbles) >= self._config.max_visible:
            oldest = self._bubbles[0]
            oldest.fade_out()

        # Create bubble
        bubble = NotificationBubble(notification, self._config, self)
        bubble.clicked.connect(self._on_bubble_clicked)
        bubble.dismissed.connect(self._on_bubble_dismissed)

        # Position bubble
        y_pos = self.TOP_MARGIN
        for existing in self._bubbles:
            y_pos += existing.height() + self._config.spacing

        bubble.move(20, y_pos)
        bubble.show()
        bubble.slide_in(-100)

        self._bubbles.append(bubble)

        # Determine duration
        duration = notification.duration_ms
        if duration is None:
            if notification.type == NotificationType.CHAT_TELL:
                duration = self._config.tell_duration_ms
            elif notification.type == NotificationType.BUFF_WARNING:
                duration = self._config.buff_warning_duration_ms
            else:
                duration = self._config.default_duration_ms

        bubble.start_dismiss_timer(duration)

        # Play sound for tells
        if notification.type == NotificationType.CHAT_TELL and self._config.play_sound_on_tell:
            play_notification_sound()

        self.update_mask()  # This will show the window if needed

    def _on_bubble_clicked(self, notification: Notification) -> None:
        """Handle bubble click."""
        self.bubble_clicked.emit(notification)

    def _on_bubble_dismissed(self, bubble: NotificationBubble) -> None:
        """Handle bubble dismissal."""
        if bubble in self._bubbles:
            self._bubbles.remove(bubble)
            bubble.deleteLater()

        # Reposition remaining bubbles
        y_pos = self.TOP_MARGIN
        for b in self._bubbles:
            b.move(20, y_pos)
            y_pos += b.height() + self._config.spacing

        self.update_mask()  # This will hide if no bubbles remain

    def clear_all(self) -> None:
        """Dismiss all notifications."""
        for bubble in self._bubbles[:]:
            bubble.fade_out()
