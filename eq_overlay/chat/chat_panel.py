"""
Chat panel - main chat window component.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QBrush, QPen
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QScrollArea,
    QLineEdit,
    QStackedWidget,
    QFrame,
    QMenu,
)

from ..core.data import ChatMessage, Conversation, ChannelType, Notification, NotificationType
from ..core.signals import Signals
from ..core.eq_utils import send_to_eq
from ..config import Config
from ..ui.theme import Theme
from ..ui.base_window import BaseOverlayWindow
from .conversation_manager import ConversationManager
from .widgets import ConversationListItem, GlobalConversationItem, MessageBubble


class ConversationView(QFrame):
    """View for displaying messages in a conversation."""

    request_more = pyqtSignal()
    MAX_BUBBLE_WIDTH = 220
    MAX_DISPLAY_MESSAGES = 100

    def __init__(self, parent=None):
        super().__init__(parent)
        self._conversation: Optional[Conversation] = None
        self._loading_more = False

        # Cache: conv_id -> (scroll_area, message_layout, widget_list, last_msg_timestamp)
        self._conv_cache: dict[str, tuple] = {}

        self.setStyleSheet("background: transparent;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Stacked widget for conversation scroll areas
        self._stack = QStackedWidget()
        layout.addWidget(self._stack)

        self._current_scroll = None

    def _create_scroll_area(self) -> tuple:
        """Create a new scroll area for a conversation."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical {
                background: rgba(40, 40, 50, 0.5);
                width: 6px;
            }
            QScrollBar::handle:vertical {
                background: rgba(100, 100, 120, 0.7);
                border-radius: 3px;
                min-height: 20px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        msg_layout = QVBoxLayout(container)
        msg_layout.setContentsMargins(8, 8, 8, 8)
        msg_layout.setSpacing(4)
        msg_layout.addStretch()

        scroll.setWidget(container)
        scroll.verticalScrollBar().valueChanged.connect(self._on_scroll)

        self._stack.addWidget(scroll)
        return (scroll, msg_layout, [])

    def _on_scroll(self, value: int) -> None:
        if value == 0 and not self._loading_more and self._conversation:
            if self._conversation.messages:
                self._loading_more = True
                self.request_more.emit()

    def set_loading(self, loading: bool) -> None:
        self._loading_more = loading

    def _scroll_to_bottom(self) -> None:
        """Scroll current view to bottom."""
        if self._current_scroll:
            # Force layout update first
            self._current_scroll.widget().updateGeometry()
            from PyQt6.QtWidgets import QApplication
            QApplication.processEvents()
            sb = self._current_scroll.verticalScrollBar()
            sb.setValue(sb.maximum())

    def set_conversation(self, conversation: Conversation) -> None:
        """Display a conversation."""
        self._conversation = conversation
        conv_id = conversation.id
        is_global = conv_id == ConversationManager.GLOBAL_ID

        all_msgs = sorted(conversation.messages, key=lambda m: m.timestamp)
        messages_to_show = all_msgs[-self.MAX_DISPLAY_MESSAGES:]

        # Check cache
        if conv_id in self._conv_cache:
            scroll, msg_layout, widgets, cached_last_ts = self._conv_cache[conv_id]

            new_last_ts = messages_to_show[-1].timestamp if messages_to_show else None

            if new_last_ts and cached_last_ts and new_last_ts > cached_last_ts:
                new_msgs = [m for m in messages_to_show if m.timestamp > cached_last_ts]

                if new_msgs:
                    last_sender = widgets[-1]._message.sender if widgets else None
                    last_time = widgets[-1]._message.timestamp if widgets else None
                    last_channel = widgets[-1]._message.channel if widgets else None

                    for msg in new_msgs:
                        show_sender = True
                        if not is_global and last_sender == msg.sender and last_time:
                            if (msg.timestamp - last_time).total_seconds() < 120:
                                if last_channel == msg.channel:
                                    show_sender = False

                        widget = MessageBubble(msg, show_sender, self.MAX_BUBBLE_WIDTH)
                        count = msg_layout.count()
                        msg_layout.insertWidget(count - 1, widget)
                        widgets.append(widget)

                        last_sender = msg.sender
                        last_time = msg.timestamp
                        last_channel = msg.channel

                    self._conv_cache[conv_id] = (scroll, msg_layout, widgets, new_last_ts)

            self._stack.setCurrentWidget(scroll)
            self._current_scroll = scroll

            def do_scroll():
                scroll.widget().updateGeometry()
                from PyQt6.QtWidgets import QApplication
                QApplication.processEvents()
                scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())

            QTimer.singleShot(0, do_scroll)
            QTimer.singleShot(50, do_scroll)
            return

        # Create new cache entry
        scroll, msg_layout, widgets = self._create_scroll_area()

        last_sender = None
        last_time = None
        last_channel = None

        for msg in messages_to_show:
            show_sender = True
            if not is_global and last_sender == msg.sender and last_time:
                if (msg.timestamp - last_time).total_seconds() < 120:
                    if last_channel == msg.channel:
                        show_sender = False

            widget = MessageBubble(msg, show_sender, self.MAX_BUBBLE_WIDTH)
            count = msg_layout.count()
            msg_layout.insertWidget(count - 1, widget)
            widgets.append(widget)

            last_sender = msg.sender
            last_time = msg.timestamp
            last_channel = msg.channel

        last_ts = messages_to_show[-1].timestamp if messages_to_show else None
        self._conv_cache[conv_id] = (scroll, msg_layout, widgets, last_ts)

        self._stack.setCurrentWidget(scroll)
        self._current_scroll = scroll

        def do_scroll():
            scroll.widget().updateGeometry()
            from PyQt6.QtWidgets import QApplication
            QApplication.processEvents()
            scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())

        QTimer.singleShot(0, do_scroll)
        QTimer.singleShot(50, do_scroll)

    def add_message(self, msg: ChatMessage, animate: bool = True) -> None:
        """Add a new message to the current conversation view."""
        if not self._conversation:
            return

        conv_id = self._conversation.id
        is_global = conv_id == ConversationManager.GLOBAL_ID

        if conv_id not in self._conv_cache:
            return

        scroll, msg_layout, widgets, _ = self._conv_cache[conv_id]

        show_sender = True
        if widgets and not is_global:
            last_widget = widgets[-1]
            last_msg = last_widget._message
            if last_msg.sender == msg.sender and last_msg.channel == msg.channel:
                if (msg.timestamp - last_msg.timestamp).total_seconds() < 120:
                    show_sender = False

        widget = MessageBubble(msg, show_sender, self.MAX_BUBBLE_WIDTH)
        
        # Check if we're at or near the bottom BEFORE adding
        sb = scroll.verticalScrollBar()
        was_at_bottom = (sb.maximum() - sb.value()) < 50
        
        count = msg_layout.count()
        msg_layout.insertWidget(count - 1, widget)
        widgets.append(widget)

        self._conv_cache[conv_id] = (scroll, msg_layout, widgets, msg.timestamp)

        if animate:
            QTimer.singleShot(50, widget.flash)

        # Only auto-scroll if user was at bottom
        if was_at_bottom:
            def do_scroll():
                # Force layout update first
                scroll.widget().updateGeometry()
                from PyQt6.QtWidgets import QApplication
                QApplication.processEvents()
                sb.setValue(sb.maximum())

            # Multiple attempts to ensure layout is complete
            QTimer.singleShot(0, do_scroll)
            QTimer.singleShot(50, do_scroll)
            QTimer.singleShot(100, do_scroll)


class ChatPanel(BaseOverlayWindow):
    """
    Main chat panel window.
    
    Shows conversation list on left, messages on right.
    """

    def __init__(self, signals: Signals, config: Config, conv_manager: ConversationManager, character_name: str):
        super().__init__(
            f"EQ Chat - {character_name}",
            config.chat_window,
            config,
            None,
        )

        self._signals = signals
        self._conv_manager = conv_manager
        self._character_name = character_name
        self._current_conversation_id: Optional[str] = None
        self._show_notifications = True

        # Build UI
        self._build_ui()

        # Connect signals
        signals.chat_message_received.connect(self._on_message_received)

        # Load settings
        self._load_settings()

        # Default to global view
        self._select_conversation(ConversationManager.GLOBAL_ID)

    def _build_ui(self) -> None:
        """Build the chat panel UI."""
        # Use the container's content layout from base class
        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        self._content_layout.addLayout(main_layout)

        # Left sidebar - conversation list
        sidebar = QFrame()
        sidebar.setFixedWidth(self._app_config.chat_window.sidebar_width)
        sidebar.setStyleSheet(f"""
            QFrame {{
                background-color: rgba(25, 25, 35, 250);
                border-right: 1px solid rgba(60, 60, 80, 150);
            }}
        """)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)

        # Conversation list scroll area
        conv_scroll = QScrollArea()
        conv_scroll.setWidgetResizable(True)
        conv_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        conv_scroll.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:vertical { width: 4px; background: transparent; }
            QScrollBar::handle:vertical { background: rgba(100, 100, 120, 0.5); border-radius: 2px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)

        self._conv_list_widget = QWidget()
        self._conv_list_widget.setStyleSheet("background: transparent;")
        self._conv_list_layout = QVBoxLayout(self._conv_list_widget)
        self._conv_list_layout.setContentsMargins(0, 0, 0, 0)
        self._conv_list_layout.setSpacing(0)
        self._conv_list_layout.addStretch()

        conv_scroll.setWidget(self._conv_list_widget)
        sidebar_layout.addWidget(conv_scroll)

        main_layout.addWidget(sidebar)

        # Right side - messages and input
        right_panel = QFrame()
        right_panel.setStyleSheet("background: transparent;")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        # Conversation view
        self._conv_view = ConversationView()
        right_layout.addWidget(self._conv_view, 1)

        # Random winner button (hidden by default)
        self._winner_button_container = QFrame()
        self._winner_button_container.setStyleSheet("""
            QFrame {
                background-color: rgba(30, 30, 40, 200);
                border-top: 1px solid rgba(60, 60, 80, 150);
            }
        """)
        winner_layout = QHBoxLayout(self._winner_button_container)
        winner_layout.setContentsMargins(8, 6, 8, 6)
        
        from PyQt6.QtWidgets import QPushButton
        
        self._clear_button = QPushButton("🔄 Clear")
        self._clear_button.setStyleSheet("""
            QPushButton {
                background-color: rgba(100, 100, 110, 180);
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: rgba(120, 120, 130, 200);
            }
            QPushButton:pressed {
                background-color: rgba(80, 80, 90, 200);
            }
        """)
        self._clear_button.clicked.connect(self._clear_random_rolls)
        
        self._winner_button = QPushButton("🎲 Pick Winner")
        self._winner_button.setStyleSheet("""
            QPushButton {
                background-color: rgba(70, 130, 90, 200);
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(90, 150, 110, 220);
            }
            QPushButton:pressed {
                background-color: rgba(60, 110, 80, 220);
            }
        """)
        self._winner_button.clicked.connect(self._pick_random_winner)
        
        winner_layout.addStretch()
        winner_layout.addWidget(self._clear_button)
        winner_layout.addWidget(self._winner_button)
        winner_layout.addStretch()
        self._winner_button_container.hide()
        right_layout.addWidget(self._winner_button_container)

        # Input field
        self._input_field = QLineEdit()
        self._input_field.setPlaceholderText("Type a message...")
        self._input_field.setStyleSheet(f"""
            QLineEdit {{
                background-color: rgba({Theme.BG_INPUT.red()}, {Theme.BG_INPUT.green()}, {Theme.BG_INPUT.blue()}, {Theme.BG_INPUT.alpha()});
                color: white;
                border: 1px solid rgba(60, 60, 80, 150);
                border-radius: 8px;
                padding: 10px 15px;
                font-size: 12px;
                margin: 8px;
            }}
            QLineEdit:focus {{
                border: 1px solid rgba(100, 130, 200, 200);
            }}
        """)
        self._input_field.returnPressed.connect(self._send_message)
        right_layout.addWidget(self._input_field)

        main_layout.addWidget(right_panel, 1)

        # Populate conversation list
        self._conv_items: dict[str, ConversationListItem] = {}
        self._global_item: Optional[GlobalConversationItem] = None
        self._refresh_conversation_list()

    def _refresh_conversation_list(self) -> None:
        """Refresh the conversation list."""
        # Clear existing
        while self._conv_list_layout.count() > 1:
            item = self._conv_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._conv_items.clear()

        # Add Global item
        global_conv = self._conv_manager.get_conversation(ConversationManager.GLOBAL_ID)
        is_selected = self._current_conversation_id == ConversationManager.GLOBAL_ID
        self._global_item = GlobalConversationItem(global_conv, is_selected, self._conv_manager)
        self._global_item.clicked.connect(self._select_conversation)
        self._global_item.config_changed.connect(self._on_global_config_changed)
        self._conv_list_layout.insertWidget(0, self._global_item)

        # Add channel and DM conversations
        idx = 1
        for conv in self._conv_manager.get_all_conversations():
            if conv.channel == ChannelType.SAY:
                continue  # Skip SAY channel

            is_selected = self._current_conversation_id == conv.id
            item = ConversationListItem(conv, is_selected)
            item.clicked.connect(self._select_conversation)
            self._conv_items[conv.id] = item
            self._conv_list_layout.insertWidget(idx, item)
            idx += 1

    def _select_conversation(self, conv_id: str) -> None:
        """Select a conversation to display."""
        self._current_conversation_id = conv_id

        # Mark as read
        if conv_id != ConversationManager.GLOBAL_ID:
            self._conv_manager.mark_read(conv_id)

        # Update selection state in list items
        if self._global_item:
            self._global_item.update_conversation(
                self._conv_manager.get_conversation(ConversationManager.GLOBAL_ID),
                conv_id == ConversationManager.GLOBAL_ID
            )

        for cid, item in self._conv_items.items():
            conv = self._conv_manager.get_conversation(cid)
            if conv:
                item.update_conversation(conv, cid == conv_id)
                if cid == conv_id:
                    item.stop_glow()

        # Display conversation
        conv = self._conv_manager.get_conversation(conv_id)
        if conv:
            self._conv_view.set_conversation(conv)

        # Show/hide winner button for Random channel
        self._winner_button_container.setVisible(conv_id == "random")

    def _on_global_config_changed(self) -> None:
        """Handle global view configuration change."""
        if self._current_conversation_id == ConversationManager.GLOBAL_ID:
            conv = self._conv_manager.get_conversation(ConversationManager.GLOBAL_ID)
            if conv:
                self._conv_view.set_conversation(conv)

    def _on_message_received(self, msg: ChatMessage) -> None:
        """Handle incoming chat message."""
        # Add to conversation manager
        conv = self._conv_manager.add_message(msg)
        if not conv:
            return

        conv_id = msg.conversation_id

        # Update unread count if not viewing this conversation
        if conv_id != self._current_conversation_id:
            self._conv_manager.increment_unread(conv_id)

        # Create conversation item if it doesn't exist (new tell, etc.)
        if conv_id not in self._conv_items and conv_id != ConversationManager.GLOBAL_ID:
            self._add_conversation_item(conv_id, conv)

        # Flash the conversation item if not viewing
        if conv_id != self._current_conversation_id and conv_id in self._conv_items:
            self._conv_items[conv_id].flash_glow(msg.channel == ChannelType.TELL)

        # For tells, move to top of tell section (most recent activity)
        if msg.channel == ChannelType.TELL and conv_id in self._conv_items:
            self._move_tell_to_top(conv_id)

        # Check for duplicate random rolls in real-time
        if msg.channel == ChannelType.RANDOM:
            self._check_random_duplicate(msg, conv)

        # If viewing this conversation (or global which includes it), add to view
        if conv_id == self._current_conversation_id:
            self._conv_view.add_message(msg)
        elif self._current_conversation_id == ConversationManager.GLOBAL_ID:
            # Check if this channel is in global view
            if msg.channel == ChannelType.TELL:
                if "tell" in self._conv_manager.get_global_channels():
                    self._conv_view.add_message(msg)
            elif msg.channel.value in self._conv_manager.get_global_channels():
                self._conv_view.add_message(msg)

        # Update conversation list item
        if conv_id in self._conv_items:
            self._conv_items[conv_id].update_conversation(
                conv, conv_id == self._current_conversation_id
            )

        # Create notifications for all incoming messages
        if self._show_notifications and not msg.is_outgoing:
            # Don't notify if viewing that conversation (unless it's global view)
            viewing_this = (conv_id == self._current_conversation_id) and self.isVisible()
            
            # For global view, check if we're viewing the relevant channel
            if self._current_conversation_id == ConversationManager.GLOBAL_ID and self.isVisible():
                if msg.channel == ChannelType.TELL:
                    viewing_this = "tell" in self._conv_manager.get_global_channels()
                else:
                    viewing_this = msg.channel.value in self._conv_manager.get_global_channels()
            
            if not viewing_this:
                notif = Notification(
                    type=NotificationType.CHAT_TELL if msg.channel == ChannelType.TELL else NotificationType.CHAT_MESSAGE,
                    title=msg.sender,
                    message=msg.content,
                    channel=msg.channel,
                    conversation_id=conv_id,
                )
                self._signals.notification_requested.emit(notif)

    def _check_random_duplicate(self, msg: ChatMessage, conv: Conversation) -> None:
        """Check if this roll is a duplicate and add DQ message if so."""
        from datetime import timedelta
        ROLL_TIMEOUT = timedelta(minutes=5)
        
        # Parse the roll to get the range
        content = msg.content
        if "(" not in content or "-" not in content:
            return
        
        try:
            range_str = content.split("(")[1].rstrip(")")
            low, high = range_str.split("-")
            max_val = int(high)
        except (ValueError, IndexError):
            return
        
        # Look back for previous rolls from same player in same range
        # Stop at separators or timeout
        player = msg.sender.lower()
        roll_count = 0
        
        for prev_msg in reversed(conv.messages[:-1]):  # Exclude current message
            # Stop at separator
            if prev_msg.sender == "System":
                break
            
            # Stop at timeout
            if (msg.timestamp - prev_msg.timestamp) > ROLL_TIMEOUT:
                break
            
            # Check if same player, same range
            if prev_msg.sender.lower() == player:
                prev_content = prev_msg.content
                if "(" in prev_content and "-" in prev_content:
                    try:
                        prev_range = prev_content.split("(")[1].rstrip(")")
                        prev_low, prev_high = prev_range.split("-")
                        prev_max = int(prev_high)
                        if prev_max == max_val:
                            roll_count += 1
                    except (ValueError, IndexError):
                        continue
        
        # If this is their second+ roll, DQ them
        if roll_count >= 1:
            from datetime import datetime
            dq_msg = ChatMessage(
                timestamp=datetime.now(),
                channel=ChannelType.RANDOM,
                sender="System",
                content=f"⛔ {msg.sender} DQ - multiple rolls (0-{max_val})",
                is_outgoing=False,
            )
            conv.messages.append(dq_msg)
            
            # Add to view if we're watching random
            if self._current_conversation_id == "random":
                self._conv_view.add_message(dq_msg)

    def _move_tell_to_top(self, conv_id: str) -> None:
        """Move a tell conversation to the top of the tells section."""
        if conv_id not in self._conv_items:
            return
        
        item = self._conv_items[conv_id]
        
        # Find first tell position (after channels)
        first_tell_pos = None
        for i in range(self._conv_list_layout.count()):
            widget = self._conv_list_layout.itemAt(i).widget()
            if widget and hasattr(widget, '_conversation'):
                if widget._conversation.id.startswith("tell:"):
                    first_tell_pos = i
                    break
        
        if first_tell_pos is None:
            return  # No tells found, shouldn't happen
        
        # Get current position of this item
        current_pos = self._conv_list_layout.indexOf(item)
        
        # If already at top of tells, nothing to do
        if current_pos == first_tell_pos:
            return
        
        # Remove and re-insert at top of tells
        self._conv_list_layout.removeWidget(item)
        self._conv_list_layout.insertWidget(first_tell_pos, item)

    def _add_conversation_item(self, conv_id: str, conv: Conversation) -> None:
        """Add a new conversation item to the list."""
        is_selected = conv_id == self._current_conversation_id
        item = ConversationListItem(conv, is_selected)
        item.clicked.connect(self._select_conversation)

        self._conv_items[conv_id] = item

        # Insert before the stretch (at end of list but before stretch)
        # Find position - tells should go after channels
        insert_pos = self._conv_list_layout.count() - 1  # Before stretch
        
        # If it's a tell, insert at the end (before stretch)
        # If it's a channel, insert after global but before tells
        if not conv_id.startswith("tell:"):
            # It's a channel - find where channels end
            for i in range(self._conv_list_layout.count()):
                widget = self._conv_list_layout.itemAt(i).widget()
                if widget and hasattr(widget, '_conversation'):
                    if widget._conversation.id.startswith("tell:"):
                        insert_pos = i
                        break

        self._conv_list_layout.insertWidget(insert_pos, item)

    def _send_message(self) -> None:
        """Send a message to EQ."""
        text = self._input_field.text().strip()
        print(f"DEBUG _send_message called, text from field: '{text}'")
        if not text:
            return

        # Clear immediately to prevent double-send
        self._input_field.clear()
        self._input_field.setEnabled(False)  # Disable during send
        
        # Re-enable after a short delay
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(300, lambda: self._input_field.setEnabled(True))

        # Determine output channel
        if self._current_conversation_id == ConversationManager.GLOBAL_ID:
            output_channel = self._conv_manager.get_global_output_channel()
            conv = self._conv_manager.get_conversation(output_channel)
        else:
            conv = self._conv_manager.get_conversation(self._current_conversation_id)

        if not conv:
            return

        # Build command
        if conv.channel == ChannelType.GUILD:
            command = f"/gu {text}"
        elif conv.channel == ChannelType.OOC:
            command = f"/ooc {text}"
        elif conv.channel == ChannelType.GROUP:
            command = f"/g {text}"
        elif conv.channel == ChannelType.SHOUT:
            command = f"/shout {text}"
        elif conv.channel == ChannelType.AUCTION:
            command = f"/auction {text}"
        elif conv.channel == ChannelType.TELL:
            command = f"/tell {conv.name} {text}"
        else:
            return

        print(f"DEBUG SEND: command='{command}'")
        send_to_eq(command)

        # Clear focus
        self._input_field.clearFocus()
        self.clearFocus()

        # Clear focus
        self._input_field.clearFocus()
        self.clearFocus()

    def _clear_random_rolls(self) -> None:
        """Add a separator to start a new round without picking a winner."""
        conv = self._conv_manager.get_conversation("random")
        if not conv:
            return

        from datetime import datetime
        separator_msg = ChatMessage(
            timestamp=datetime.now(),
            channel=ChannelType.RANDOM,
            sender="System",
            content="── New Round ──",
            is_outgoing=False,
        )
        
        conv.messages.append(separator_msg)
        self._conv_view.set_conversation(conv)
        QTimer.singleShot(50, self._conv_view._scroll_to_bottom)

    def _get_recent_rolls(self) -> dict[int, list[tuple[str, int, ChatMessage]]]:
        """Get recent rolls grouped by range, with duplicate rollers excluded."""
        conv = self._conv_manager.get_conversation("random")
        if not conv or not conv.messages:
            return {}

        from datetime import datetime, timedelta
        ROLL_TIMEOUT = timedelta(minutes=5)

        # Collect all rolls since last separator, respecting timeout
        all_rolls: list[tuple[str, int, int, ChatMessage]] = []  # (player, roll, max, msg)
        last_roll_time = None
        
        for msg in reversed(conv.messages):
            # Check if this is a separator
            if msg.sender == "System":
                break
            
            # Check timeout
            if last_roll_time and (last_roll_time - msg.timestamp) > ROLL_TIMEOUT:
                break
            
            # Parse roll: "42 (0-100)"
            content = msg.content
            if "(" in content and "-" in content:
                try:
                    roll_str = content.split("(")[0].strip()
                    range_str = content.split("(")[1].rstrip(")")
                    low, high = range_str.split("-")
                    roll = int(roll_str)
                    max_val = int(high)
                    all_rolls.append((msg.sender, roll, max_val, msg))
                    last_roll_time = msg.timestamp
                except (ValueError, IndexError):
                    continue

        # Group by range
        by_range: dict[int, list[tuple[str, int, ChatMessage]]] = {}
        for player, roll, max_val, msg in all_rolls:
            if max_val not in by_range:
                by_range[max_val] = []
            by_range[max_val].append((player, roll, msg))

        # For each range, find and exclude duplicate rollers
        result: dict[int, list[tuple[str, int, ChatMessage]]] = {}
        disqualified: dict[int, list[str]] = {}  # Track DQ'd players per range
        
        for max_val, rolls in by_range.items():
            # Count rolls per player
            player_rolls: dict[str, list[tuple[int, ChatMessage]]] = {}
            for player, roll, msg in rolls:
                player_lower = player.lower()
                if player_lower not in player_rolls:
                    player_rolls[player_lower] = []
                player_rolls[player_lower].append((roll, msg))
            
            # Only include players who rolled exactly once
            valid_rolls = []
            dq_players = []
            for player, roll, msg in rolls:
                if len(player_rolls[player.lower()]) == 1:
                    valid_rolls.append((player, roll, msg))
                elif player not in dq_players:
                    dq_players.append(player)
            
            if valid_rolls:
                result[max_val] = valid_rolls
            if dq_players:
                disqualified[max_val] = dq_players

        # Add DQ messages for any disqualified players
        if disqualified:
            from datetime import datetime
            conv = self._conv_manager.get_conversation("random")
            if conv:
                for max_val, players in disqualified.items():
                    for player in players:
                        dq_msg = ChatMessage(
                            timestamp=datetime.now(),
                            channel=ChannelType.RANDOM,
                            sender="System",
                            content=f"⛔ {player} DQ - multiple rolls (0-{max_val})",
                            is_outgoing=False,
                        )
                        # Only add if not already DQ'd in this session
                        already_dq = any(
                            m.sender == "System" and f"⛔ {player} DQ" in m.content
                            for m in conv.messages[-20:]  # Check recent messages
                        )
                        if not already_dq:
                            conv.messages.append(dq_msg)
                
                self._conv_view.set_conversation(conv)

        return result

    def _pick_random_winner(self) -> None:
        """Pick the winner from recent rolls and add a separator."""
        by_range = self._get_recent_rolls()
        
        if not by_range:
            return

        from datetime import datetime
        conv = self._conv_manager.get_conversation("random")
        if not conv:
            return

        # If multiple ranges, show selection menu
        if len(by_range) > 1:
            menu = QMenu(self)
            menu.setStyleSheet("""
                QMenu {
                    background-color: rgba(40, 40, 50, 250);
                    color: white;
                    border: 1px solid rgba(80, 80, 100, 200);
                    padding: 4px;
                }
                QMenu::item {
                    padding: 6px 20px;
                }
                QMenu::item:selected {
                    background-color: rgba(70, 130, 90, 200);
                }
            """)
            
            for max_val in sorted(by_range.keys()):
                rolls = by_range[max_val]
                action = menu.addAction(f"0-{max_val} ({len(rolls)} valid rolls)")
                action.setData(max_val)
            
            action = menu.exec(self._winner_button.mapToGlobal(self._winner_button.rect().topLeft()))
            if not action:
                return
            selected_range = action.data()
            rolls = by_range[selected_range]
        else:
            # Single range
            selected_range = list(by_range.keys())[0]
            rolls = by_range[selected_range]

        if not rolls:
            return

        # Find highest roll
        winner = max(rolls, key=lambda x: x[1])
        winner_name, winner_roll, _ = winner

        # Create winner announcement
        winner_msg = ChatMessage(
            timestamp=datetime.now(),
            channel=ChannelType.RANDOM,
            sender="System",
            content=f"🏆 WINNER: {winner_name} with {winner_roll}! (0-{selected_range})",
            is_outgoing=False,
        )
        
        conv.messages.append(winner_msg)
        self._conv_view.set_conversation(conv)
        QTimer.singleShot(50, self._conv_view._scroll_to_bottom)

    def _load_settings(self) -> None:
        """Load panel settings."""
        settings_file = self._app_config.get_settings_file()
        if settings_file.exists():
            try:
                import json
                with open(settings_file, "r") as f:
                    settings = json.load(f)
                self._auto_hide = settings.get("chat_auto_hide", True)
                self._show_notifications = settings.get("show_notifications", True)
                opacity = settings.get("chat_opacity", self._window_config.opacity)
                self.setWindowOpacity(opacity)
            except Exception:
                pass

    def save_settings(self) -> None:
        """Save panel settings."""
        self._app_config.paths.data_dir.mkdir(parents=True, exist_ok=True)
        settings_file = self._app_config.get_settings_file()
        try:
            import json
            # Load existing
            settings = {}
            if settings_file.exists():
                with open(settings_file, "r") as f:
                    settings = json.load(f)

            settings["chat_auto_hide"] = self._auto_hide
            settings["show_notifications"] = self._show_notifications
            settings["chat_opacity"] = self.windowOpacity()

            with open(settings_file, "w") as f:
                json.dump(settings, f)
        except Exception:
            pass

    def _add_context_menu_items(self, menu: QMenu) -> None:
        """Add chat-specific context menu items."""
        notif_action = menu.addAction("Show notification bubbles")
        notif_action.setCheckable(True)
        notif_action.setChecked(self._show_notifications)
        notif_action.triggered.connect(lambda checked: setattr(self, '_show_notifications', checked))

    def closeEvent(self, event):
        self.save_settings()
        self._conv_manager.save()
        event.accept()
