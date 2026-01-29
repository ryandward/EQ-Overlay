"""
Settings dialog with font picker and other configuration options.
"""

from __future__ import annotations

import json

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QDoubleSpinBox, QSpinBox, QGroupBox, QFrame,
    QDialogButtonBox, QMessageBox, QCheckBox,
)

from .theme import Theme


class SettingsDialog(QDialog):
    """Settings dialog with font configuration."""
    
    settings_changed = pyqtSignal()  # Emitted when settings are saved
    
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self._config = config
        self._config_path = config.config_path
        
        self.setWindowTitle("EQ Overlay Settings")
        self.setMinimumWidth(400)
        self.setStyleSheet(f"""
            QDialog {{
                background-color: rgb(45, 45, 55);
                color: white;
            }}
            QGroupBox {{
                {Theme.css_font_md(bold=True)}
                border: 1px solid rgba(80, 80, 100, 150);
                border-radius: 6px;
                margin-top: 12px;
                padding-top: 8px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }}
            QLabel {{
                {Theme.css_font_md()}
            }}
            QComboBox, QDoubleSpinBox, QSpinBox {{
                {Theme.css_font_md()}
                background-color: rgb(55, 55, 65);
                border: 1px solid rgba(80, 80, 100, 150);
                border-radius: 4px;
                padding: 5px 10px;
                color: white;
            }}
            QComboBox::drop-down {{
                border: none;
                width: 20px;
            }}
            QComboBox::down-arrow {{
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 6px solid white;
                margin-right: 5px;
            }}
            QComboBox QAbstractItemView {{
                background-color: rgb(55, 55, 65);
                color: white;
                selection-background-color: rgb(70, 100, 150);
            }}
            QPushButton {{
                {Theme.css_font_md()}
                background-color: rgb(60, 90, 140);
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                color: white;
            }}
            QPushButton:hover {{
                background-color: rgb(70, 100, 160);
            }}
            QPushButton:pressed {{
                background-color: rgb(50, 80, 130);
            }}
        """)
        
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Font settings group
        font_group = QGroupBox("Font Settings")
        font_layout = QVBoxLayout(font_group)
        font_layout.setSpacing(12)
        
        # Font family
        family_row = QHBoxLayout()
        family_label = QLabel("Font Family:")
        family_label.setFixedWidth(100)
        self._font_combo = QComboBox()
        self._font_combo.setMaxVisibleItems(15)
        
        # Populate with available fonts
        available_fonts = Theme.get_available_fonts()
        self._font_combo.addItems(available_fonts)
        
        # Select current font
        current_font = Theme.font_family()
        idx = self._font_combo.findText(current_font)
        if idx >= 0:
            self._font_combo.setCurrentIndex(idx)
        
        self._font_combo.currentTextChanged.connect(self._update_preview)
        
        family_row.addWidget(family_label)
        family_row.addWidget(self._font_combo, 1)
        font_layout.addLayout(family_row)
        
        # Font scale
        scale_row = QHBoxLayout()
        scale_label = QLabel("Font Scale:")
        scale_label.setFixedWidth(100)
        self._scale_spin = QDoubleSpinBox()
        self._scale_spin.setRange(0.5, 2.0)
        self._scale_spin.setSingleStep(0.1)
        self._scale_spin.setValue(self._config.font.scale)
        self._scale_spin.valueChanged.connect(self._update_preview)
        
        scale_row.addWidget(scale_label)
        scale_row.addWidget(self._scale_spin)
        scale_row.addStretch()
        font_layout.addLayout(scale_row)
        
        # Preview
        preview_label = QLabel("Preview:")
        font_layout.addWidget(preview_label)
        
        self._preview_frame = QFrame()
        self._preview_frame.setStyleSheet("""
            QFrame {
                background-color: rgb(35, 35, 45);
                border: 1px solid rgba(80, 80, 100, 150);
                border-radius: 4px;
                padding: 10px;
            }
        """)
        preview_layout = QVBoxLayout(self._preview_frame)
        
        # Store base sizes for preview (before scaling)
        self._preview_labels = []
        self._base_sizes = [
            ("XS", 9),
            ("SM", 10),
            ("MD", 11),
            ("LG", 12),
            ("XL", 13),
        ]
        for name, base_size in self._base_sizes:
            lbl = QLabel()
            lbl.setWordWrap(True)
            self._preview_labels.append((lbl, name, base_size))
            preview_layout.addWidget(lbl)
        
        font_layout.addWidget(self._preview_frame)
        layout.addWidget(font_group)
        
        # Window settings group
        window_group = QGroupBox("Window Settings")
        window_layout = QVBoxLayout(window_group)
        window_layout.setSpacing(8)
        
        # Chat window width
        chat_width_row = QHBoxLayout()
        chat_width_label = QLabel("Chat Panel Width:")
        chat_width_label.setFixedWidth(120)
        self._chat_width_spin = QSpinBox()
        self._chat_width_spin.setRange(200, 600)
        self._chat_width_spin.setSingleStep(10)
        self._chat_width_spin.setValue(self._config.chat_window.width)
        self._chat_width_spin.setSuffix(" px")
        chat_width_row.addWidget(chat_width_label)
        chat_width_row.addWidget(self._chat_width_spin)
        chat_width_row.addStretch()
        window_layout.addLayout(chat_width_row)
        
        # Timer window width
        timer_width_row = QHBoxLayout()
        timer_width_label = QLabel("Timer Panel Width:")
        timer_width_label.setFixedWidth(120)
        self._timer_width_spin = QSpinBox()
        self._timer_width_spin.setRange(150, 500)
        self._timer_width_spin.setSingleStep(10)
        self._timer_width_spin.setValue(self._config.timers_window.width)
        self._timer_width_spin.setSuffix(" px")
        timer_width_row.addWidget(timer_width_label)
        timer_width_row.addWidget(self._timer_width_spin)
        timer_width_row.addStretch()
        window_layout.addLayout(timer_width_row)
        
        # Sidebar width
        sidebar_width_row = QHBoxLayout()
        sidebar_width_label = QLabel("Sidebar Width:")
        sidebar_width_label.setFixedWidth(120)
        self._sidebar_width_spin = QSpinBox()
        self._sidebar_width_spin.setRange(60, 200)
        self._sidebar_width_spin.setSingleStep(10)
        self._sidebar_width_spin.setValue(self._config.chat_window.sidebar_width)
        self._sidebar_width_spin.setSuffix(" px")
        sidebar_width_row.addWidget(sidebar_width_label)
        sidebar_width_row.addWidget(self._sidebar_width_spin)
        sidebar_width_row.addStretch()
        window_layout.addLayout(sidebar_width_row)
        
        layout.addWidget(window_group)
        
        # Chat settings group
        chat_group = QGroupBox("Chat Settings")
        chat_layout = QVBoxLayout(chat_group)
        chat_layout.setSpacing(8)
        
        # Bold messages checkbox
        self._bold_messages_check = QCheckBox("Bold message text")
        self._bold_messages_check.setChecked(self._config.chat.bold_messages)
        self._bold_messages_check.setStyleSheet(f"""
            QCheckBox {{
                {Theme.css_font_md()}
                color: white;
            }}
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
            }}
            QCheckBox::indicator:unchecked {{
                background-color: rgb(55, 55, 65);
                border: 1px solid rgba(80, 80, 100, 150);
                border-radius: 3px;
            }}
            QCheckBox::indicator:checked {{
                background-color: rgb(60, 120, 180);
                border: 1px solid rgba(80, 120, 200, 200);
                border-radius: 3px;
            }}
        """)
        chat_layout.addWidget(self._bold_messages_check)
        
        layout.addWidget(chat_group)
        
        # Note about restart
        note = QLabel("Note: Some changes may require restart to take full effect.")
        note.setStyleSheet(f"{Theme.css_font_sm(bold=False)} color: rgba(200, 200, 200, 180);")
        layout.addWidget(note)
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        
        save_btn = QPushButton("Save")
        save_btn.clicked.connect(self._save_settings)
        save_btn.setStyleSheet("""
            QPushButton {
                background-color: rgb(60, 130, 90);
            }
            QPushButton:hover {
                background-color: rgb(70, 150, 100);
            }
        """)
        
        button_layout.addWidget(cancel_btn)
        button_layout.addWidget(save_btn)
        layout.addLayout(button_layout)
        
        # Initial preview update
        self._update_preview()
    
    def _update_preview(self):
        """Update the preview labels with selected font."""
        family = self._font_combo.currentText()
        scale = self._scale_spin.value()
        
        for label, name, base_size in self._preview_labels:
            scaled_size = max(6, int(base_size * scale))
            label.setText(f"{name} ({scaled_size}px): The quick brown fox jumps over the lazy dog")
            label.setStyleSheet(f"font-family: '{family}', sans-serif; font-size: {scaled_size}px; color: white;")
    
    def _save_settings(self):
        """Save settings to config.json."""
        try:
            # Load current config
            with open(self._config_path, 'r') as f:
                config_data = json.load(f)
            
            # Update font settings
            if 'font' not in config_data:
                config_data['font'] = {}
            
            config_data['font']['family'] = self._font_combo.currentText()
            config_data['font']['scale'] = self._scale_spin.value()
            
            # Update window settings
            if 'windows' not in config_data:
                config_data['windows'] = {'chat': {}, 'timers': {}}
            
            config_data['windows']['chat']['width'] = self._chat_width_spin.value()
            config_data['windows']['chat']['sidebar_width'] = self._sidebar_width_spin.value()
            config_data['windows']['timers']['width'] = self._timer_width_spin.value()
            
            # Update chat settings
            if 'chat' not in config_data:
                config_data['chat'] = {}
            
            config_data['chat']['bold_messages'] = self._bold_messages_check.isChecked()
            
            # Save
            with open(self._config_path, 'w') as f:
                json.dump(config_data, f, indent=2)
            
            # Update Theme live
            self._config.font.family = self._font_combo.currentText()
            self._config.font.scale = self._scale_spin.value()
            Theme.init_fonts(self._config.font)
            
            # Update chat settings live
            self._config.chat.bold_messages = self._bold_messages_check.isChecked()
            Theme.set_chat_bold_messages(self._config.chat.bold_messages)
            
            # Note: Window size changes require restart
            
            self.settings_changed.emit()
            
            QMessageBox.information(
                self,
                "Settings Saved",
                "Settings have been saved.\nWindow size changes require restart."
            )
            self.accept()
            
        except Exception as e:
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to save settings: {e}"
            )
