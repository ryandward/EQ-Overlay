"""
Base window class with shared functionality for overlay panels.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, QTimer, QPoint
from PyQt6.QtGui import QColor, QPainter, QBrush, QPen, QMouseEvent
from PyQt6.QtWidgets import (
    QWidget, QApplication, QVBoxLayout, QHBoxLayout, 
    QMenu, QFrame, QLabel,
)

from ..config import WindowConfig, Config
from ..core.eq_utils import is_eq_focused
from .theme import Theme


class TitleBar(QFrame):
    """Custom draggable title bar - matches original styling."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self._parent = parent
        self._drag_pos: Optional[QPoint] = None
        
        self.setFixedHeight(32)
        self.setStyleSheet("""
            QFrame {
                background-color: rgba(40, 40, 60, 255);
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 8, 0)
        layout.setSpacing(8)

        self._title_label = QLabel(title)
        self._title_label.setStyleSheet(f"""
            color: white;
            {Theme.css_font_md(bold=True)}
            background: transparent;
        """)

        self._status_label = QLabel("")
        self._status_label.setStyleSheet(f"""
            color: #ffcc00;
            {Theme.css_font_sm(bold=False)}
            background: transparent;
        """)

        layout.addWidget(self._title_label)
        layout.addStretch()
        layout.addWidget(self._status_label)

    def set_status(self, text: str) -> None:
        self._status_label.setText(text)

    def set_title(self, text: str) -> None:
        self._title_label.setText(text)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton and self._parent:
            self._drag_pos = event.globalPosition().toPoint() - self._parent.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._drag_pos is not None and event.buttons() & Qt.MouseButton.LeftButton and self._parent:
            self._parent.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._drag_pos = None

    def wheelEvent(self, event):
        """Handle mouse wheel for opacity adjustment."""
        if self._parent:
            delta = event.angleDelta().y()
            current = self._parent.windowOpacity()
            if delta > 0:
                new_opacity = min(1.0, current + 0.05)
            else:
                new_opacity = max(0.3, current - 0.05)
            self._parent.setWindowOpacity(new_opacity)
            event.accept()


class BaseOverlayWindow(QWidget):
    """
    Base class for overlay windows (chat and timers panels).
    
    Provides:
    - Frameless, semi-transparent window
    - Auto-hide when EQ unfocused
    - Draggable title bar
    - Context menu
    - Opacity control
    """

    def __init__(
        self,
        title: str,
        window_config: WindowConfig,
        app_config: Config,
        parent=None,
    ):
        super().__init__(parent)
        self._title = title
        self._window_config = window_config
        self._app_config = app_config
        self._auto_hide = app_config.behavior.auto_hide_when_unfocused
        self._is_visible = True

        # Window flags
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setWindowTitle(title)
        self.setWindowOpacity(window_config.opacity)

        # Position window - full screen height like originals
        self._position_on_screen()

        # Auto-hide timer
        self._focus_timer = QTimer(self)
        self._focus_timer.timeout.connect(self._check_focus)
        self._focus_timer.start(500)

        # Main layout - NO margins, content fills window
        self._main_layout = QVBoxLayout(self)
        self._main_layout.setContentsMargins(0, 0, 0, 0)
        self._main_layout.setSpacing(0)

        # Title bar
        self._title_bar = TitleBar(title, self)
        self._main_layout.addWidget(self._title_bar)

        # Content container - this is where subclasses add their content
        # Uses QFrame with clipping stylesheet
        self._container = QFrame()
        self._container.setStyleSheet("""
            QFrame {
                background-color: rgba(15, 15, 20, 220);
                border-bottom-left-radius: 8px;
                border-bottom-right-radius: 8px;
            }
        """)
        self._main_layout.addWidget(self._container, 1)

        # Container layout for subclasses to use
        self._content_layout = QVBoxLayout(self._container)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(0)

    def _position_on_screen(self) -> None:
        """Position window on the configured side of the screen, full height."""
        screen = QApplication.primaryScreen()
        if not screen:
            return

        geo = screen.geometry()  # Full screen, not availableGeometry
        width = self._window_config.width

        if self._window_config.side == "left":
            x = 0
        else:  # right
            x = geo.width() - width

        # Full height
        self.setGeometry(x, 0, width, geo.height())

    def _check_focus(self) -> None:
        """Check if EQ has focus and show/hide accordingly."""
        if not self._auto_hide:
            if not self._is_visible:
                self.show()
                self._is_visible = True
            return

        eq_focused = is_eq_focused()
        if eq_focused and not self._is_visible:
            self.show()
            self._is_visible = True
        elif not eq_focused and self._is_visible:
            self.hide()
            self._is_visible = False

    def set_auto_hide(self, enabled: bool) -> None:
        """Enable/disable auto-hide."""
        self._auto_hide = enabled
        if not enabled and not self._is_visible:
            self.show()
            self._is_visible = True

    def set_status(self, text: str) -> None:
        """Set status text in title bar."""
        self._title_bar.set_status(text)

    def contextMenuEvent(self, event):
        """Show context menu."""
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: rgba(40, 40, 55, 250);
                border: 1px solid rgba(80, 80, 100, 200);
                border-radius: 6px;
                padding: 4px;
            }
            QMenu::item {
                color: white;
                padding: 8px 20px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: rgba(70, 70, 100, 200);
            }
        """)

        # Auto-hide toggle
        auto_hide_action = menu.addAction("Auto-hide when EQ unfocused")
        auto_hide_action.setCheckable(True)
        auto_hide_action.setChecked(self._auto_hide)
        auto_hide_action.triggered.connect(self.set_auto_hide)

        # Settings
        menu.addSeparator()
        settings_action = menu.addAction("⚙ Settings...")
        settings_action.triggered.connect(self._show_settings)

        # Add subclass-specific menu items
        self._add_context_menu_items(menu)

        menu.exec(event.globalPos())
    
    def _show_settings(self):
        """Show the settings dialog."""
        from .settings_dialog import SettingsDialog
        dialog = SettingsDialog(self._app_config, parent=self)
        dialog.settings_changed.connect(self._on_settings_changed)
        dialog.exec()
    
    def _on_settings_changed(self):
        """Handle settings changes - can be overridden by subclasses."""
        # Trigger a repaint to pick up new fonts
        self.update()

    def _add_context_menu_items(self, menu: QMenu) -> None:
        """Override in subclasses to add custom menu items."""
        pass
