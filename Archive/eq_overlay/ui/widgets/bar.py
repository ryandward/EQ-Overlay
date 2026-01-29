"""
Shared bar widget - unified styling for timer bars, DPS bars, chat bubbles, etc.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QColor, QPainter, QBrush, QPen, QLinearGradient
from PyQt6.QtWidgets import QFrame, QSizePolicy

from ..theme import Theme


class SharedBarStyle:
    """
    Shared styling constants and paint methods for bars/bubbles.
    
    All bars in the app should use these for visual consistency:
    - Timer bars
    - DPS bars  
    - Casting bar
    - Chat bubbles
    - Notification bubbles
    """
    
    # Dimensions
    BAR_HEIGHT = 28
    BAR_RADIUS = 6
    BAR_MARGIN = 4
    
    # Colors
    BG_EMPTY = QColor(30, 30, 40, 100)
    BG_FILLED = QColor(30, 30, 40, 180)
    BORDER_COLOR = QColor(255, 255, 255, 20)
    
    @staticmethod
    def draw_bar_background(
        painter: QPainter,
        rect: QRectF,
        radius: float = None,
    ) -> None:
        """Draw the empty bar background."""
        if radius is None:
            radius = SharedBarStyle.BAR_RADIUS
            
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(SharedBarStyle.BG_FILLED))
        painter.drawRoundedRect(rect, radius, radius)
    
    @staticmethod
    def draw_bar_progress(
        painter: QPainter,
        rect: QRectF,
        percent: float,
        color: QColor,
        radius: float = None,
    ) -> None:
        """Draw progress fill with gradient and shine."""
        if radius is None:
            radius = SharedBarStyle.BAR_RADIUS
            
        if percent <= 0:
            return
            
        progress_width = rect.width() * (percent / 100.0)
        if progress_width < 1:
            return
            
        # Clip to progress area
        progress_rect = QRectF(rect.x(), rect.y(), progress_width, rect.height())
        painter.setClipRect(progress_rect)
        
        # Main gradient fill
        gradient = QLinearGradient(rect.x(), 0, rect.x() + rect.width(), 0)
        gradient.setColorAt(0, color)
        gradient.setColorAt(1, color.lighter(115))
        painter.setBrush(QBrush(gradient))
        painter.drawRoundedRect(rect, radius, radius)
        
        # Shine overlay
        shine = QLinearGradient(0, rect.y(), 0, rect.y() + rect.height())
        shine.setColorAt(0, QColor(255, 255, 255, 50))
        shine.setColorAt(0.5, QColor(255, 255, 255, 15))
        shine.setColorAt(0.51, QColor(0, 0, 0, 15))
        shine.setColorAt(1, QColor(0, 0, 0, 30))
        painter.setBrush(QBrush(shine))
        painter.drawRoundedRect(rect, radius, radius)
        
        painter.setClipping(False)
    
    @staticmethod
    def draw_bar_border(
        painter: QPainter,
        rect: QRectF,
        radius: float = None,
    ) -> None:
        """Draw subtle border."""
        if radius is None:
            radius = SharedBarStyle.BAR_RADIUS
            
        painter.setPen(QPen(SharedBarStyle.BORDER_COLOR, 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect, radius, radius)
    
    @staticmethod
    def draw_shadowed_text(
        painter: QPainter,
        rect: QRectF,
        text: str,
        alignment: Qt.AlignmentFlag,
        color: QColor = None,
        shadow_color: QColor = None,
    ) -> None:
        """Draw text with drop shadow for readability."""
        if color is None:
            color = Theme.TEXT_PRIMARY
        if shadow_color is None:
            shadow_color = Theme.TEXT_SHADOW
            
        # Shadow
        shadow_rect = QRectF(rect.x() + 1, rect.y() + 1, rect.width(), rect.height())
        painter.setPen(QPen(shadow_color))
        painter.drawText(shadow_rect, alignment, text)
        
        # Main text
        painter.setPen(QPen(color))
        painter.drawText(rect, alignment, text)

    @staticmethod
    def draw_bubble(
        painter: QPainter,
        rect: QRectF,
        color: QColor,
        radius: float = None,
    ) -> None:
        """Draw a chat/notification bubble with consistent styling."""
        if radius is None:
            radius = SharedBarStyle.BAR_RADIUS
        
        # Main fill
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(color))
        painter.drawRoundedRect(rect, radius, radius)
        
        # Shine overlay (same as bars for consistency)
        shine = QLinearGradient(0, rect.y(), 0, rect.y() + rect.height())
        shine.setColorAt(0, QColor(255, 255, 255, 50))
        shine.setColorAt(0.5, QColor(255, 255, 255, 15))
        shine.setColorAt(0.51, QColor(0, 0, 0, 15))
        shine.setColorAt(1, QColor(0, 0, 0, 30))
        painter.setBrush(QBrush(shine))
        painter.drawRoundedRect(rect, radius, radius)
        
        # Border
        painter.setPen(QPen(SharedBarStyle.BORDER_COLOR, 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect, radius, radius)


class BaseBarWidget(QFrame):
    """
    Base class for all bar widgets (timers, DPS, casting).
    
    Subclasses implement paintEvent using SharedBarStyle methods.
    """
    
    def __init__(self, height: int = None, parent=None):
        super().__init__(parent)
        if height is None:
            height = SharedBarStyle.BAR_HEIGHT
        self.setFixedHeight(height)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setStyleSheet("background: transparent;")
    
    def get_bar_rect(self) -> QRectF:
        """Get the rectangle for the bar, accounting for margins."""
        m = SharedBarStyle.BAR_MARGIN
        return QRectF(m, m, self.width() - m * 2, self.height() - m * 2)
