#!/usr/bin/env python3
"""
EQ Overlay - Unified overlay for EverQuest Project 1999.

Provides:
- Chat panel (left side)
- Timer/DPS panel (right side)  
- Shared notification center
"""

from __future__ import annotations

import argparse
import os
import signal
import sys
import threading
from pathlib import Path

# Force X11 backend before importing Qt
os.environ.setdefault("QT_QPA_PLATFORM", "xcb")

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer

from .config import Config
from .core.signals import Signals
from .core.log_watcher import LogWatcher, discover_characters, find_character_log
from .core.data import Notification
from .ui.theme import Theme
from .ui.notifications import NotificationCenter
from .chat.conversation_manager import ConversationManager
from .chat.chat_panel import ChatPanel
from .timers.spell_database import SpellDatabase
from .timers.timer_manager import TimerManager
from .timers.timer_panel import TimerPanel


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="EQ Overlay")
    parser.add_argument("character", nargs="?", help="Character name")
    parser.add_argument("--config", type=Path, help="Path to config.json")
    parser.add_argument("--no-history", action="store_true", help="Don't load history")
    parser.add_argument("--chat-only", action="store_true", help="Only show chat panel")
    parser.add_argument("--timers-only", action="store_true", help="Only show timers panel")
    args = parser.parse_args()

    # Load config
    try:
        config = Config.load(args.config)
    except FileNotFoundError as e:
        print(f"ERROR: {e}")
        return 1

    # Load EQ colors from ini
    if config.paths.ini_path.exists():
        print(f"Loading colors from {config.paths.ini_path}")
        Theme.load_eq_colors(config.paths.ini_path)
    else:
        print(f"No eqclient.ini found at {config.paths.ini_path}, using default colors")

    # Find character
    if args.character:
        result = find_character_log(args.character, config)
        if not result:
            print(f"ERROR: Character '{args.character}' not found")
            return 1
        char_name, log_path = result
    else:
        chars = discover_characters(config)
        if not chars:
            print(f"ERROR: No log files found in {config.paths.log_dir}")
            return 1
        char_name, log_path, _ = chars[0]

    print(f"Character: {char_name}")
    print(f"Log: {log_path}")

    # Create Qt application
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)

    # Create shared signals
    signals = Signals()

    # Create log watcher
    watcher = LogWatcher(log_path, char_name, signals, config)

    # Create notification center
    notif_center = NotificationCenter(config.notifications)
    signals.notification_requested.connect(notif_center.show_notification)

    # Create panels
    chat_panel = None
    timer_panel = None

    if not args.timers_only:
        # Create conversation manager and chat panel
        conv_manager = ConversationManager(config, char_name)
        json_loaded = conv_manager.load()

        # Load chat history
        if not args.no_history:
            if json_loaded and conv_manager.has_data():
                latest = conv_manager.get_latest_timestamp()
                print(f"Loading chat since {latest.strftime('%Y-%m-%d %H:%M')}...")
                history = watcher.load_chat_history_since(latest)
                for msg in history:
                    conv_manager.add_message(msg)
                print(f"Found {len(history)} new messages")
            else:
                print("Bootstrapping chat history...")
                history = watcher.load_chat_history()
                for msg in history:
                    conv_manager.add_message(msg)
                print(f"Loaded {len(history)} messages")
                conv_manager.save()

        conv_manager.sort_all_messages()

        chat_panel = ChatPanel(signals, config, conv_manager, char_name)

        # Connect notification clicks to chat panel
        def on_notif_click(notif: Notification):
            if notif.conversation_id and chat_panel:
                chat_panel._select_conversation(notif.conversation_id)
                chat_panel.show()
                chat_panel.raise_()

        notif_center.bubble_clicked.connect(on_notif_click)

    if not args.chat_only:
        # Create spell database and timer manager
        spell_db = SpellDatabase(config.paths.spells_file, config.paths.whitelist_file)
        timer_mgr = TimerManager(signals)

        timer_panel = TimerPanel(
            signals, config, spell_db, timer_mgr, watcher, char_name
        )

        # Load timer history
        if not args.no_history:
            timer_panel.load_history()

    # Handle SIGINT gracefully
    def handle_sigint(*_):
        print("\nShutting down...")
        if chat_panel:
            chat_panel.save_settings()
            conv_manager.save()
        watcher.stop()
        app.quit()

    signal.signal(signal.SIGINT, handle_sigint)

    # Timer to allow SIGINT to be processed
    sigint_timer = QTimer()
    sigint_timer.timeout.connect(lambda: None)
    sigint_timer.start(100)

    # Character change detection timer (if auto-switch enabled)
    current_log_path = log_path
    
    def check_character_change():
        nonlocal current_log_path, char_name, watcher, conv_manager, chat_panel, timer_panel, watch_thread
        
        if not config.behavior.auto_switch_character:
            return
            
        chars = discover_characters(config)
        if not chars:
            return
            
        most_recent_name, most_recent_path, _ = chars[0]
        if most_recent_path != current_log_path:
            print(f"\nCharacter change detected: {char_name} -> {most_recent_name}")
            
            # Save current state
            if chat_panel:
                chat_panel.save_settings()
                conv_manager.save()
            
            # Stop current watcher
            watcher.stop()
            
            # Update tracking
            char_name = most_recent_name
            current_log_path = most_recent_path
            
            # Create new watcher
            watcher = LogWatcher(most_recent_path, most_recent_name, signals, config)
            
            # Recreate chat panel components
            if chat_panel:
                new_conv_manager = ConversationManager(config, most_recent_name)
                json_loaded = new_conv_manager.load()
                
                if json_loaded and new_conv_manager.has_data():
                    latest = new_conv_manager.get_latest_timestamp()
                    print(f"Loading chat since {latest.strftime('%Y-%m-%d %H:%M')}...")
                    history = watcher.load_chat_history_since(latest)
                    for msg in history:
                        new_conv_manager.add_message(msg)
                    print(f"Found {len(history)} new messages")
                else:
                    print("Bootstrapping chat history...")
                    history = watcher.load_chat_history()
                    for msg in history:
                        new_conv_manager.add_message(msg)
                    print(f"Loaded {len(history)} messages")
                    new_conv_manager.save()
                
                new_conv_manager.sort_all_messages()
                conv_manager = new_conv_manager
                
                # Update chat panel
                chat_panel._conv_manager = conv_manager
                chat_panel._character_name = most_recent_name
                chat_panel._title_bar.set_title(f"EQ Chat - {most_recent_name}")
                chat_panel.setWindowTitle(f"EQ Chat - {most_recent_name}")
                chat_panel._refresh_conversation_list()
                chat_panel._select_conversation(ConversationManager.GLOBAL_ID)
            
            # Recreate timer panel components
            if timer_panel:
                timer_panel._character_name = most_recent_name
                timer_panel._title_bar.set_title(f"EQ Timers - {most_recent_name}")
                timer_panel.setWindowTitle(f"EQ Timers - {most_recent_name}")
                timer_panel._timer_mgr.clear()
                timer_panel._log_watcher = watcher
                watcher.add_entry_callback(timer_panel._process_log_entry)
                if not args.no_history:
                    timer_panel.load_history()
            
            # Restart watcher thread
            watch_thread = threading.Thread(target=watcher.watch, daemon=True)
            watch_thread.start()
            
            print(f"Switched to {most_recent_name}")
    
    char_check_timer = QTimer()
    char_check_timer.timeout.connect(check_character_change)
    char_check_timer.start(2000)  # Check every 2 seconds

    # Show windows
    if chat_panel:
        chat_panel.show()
    if timer_panel:
        timer_panel.show()
    notif_center.show()

    # Start log watcher thread
    watch_thread = threading.Thread(target=watcher.watch, daemon=True)
    watch_thread.start()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
