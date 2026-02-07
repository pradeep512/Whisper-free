"""
SettingsPanel - Settings UI for configuration

Provides settings interface with:
- Grouped settings (Whisper, Audio, Hotkey, Overlay, Advanced)
- Form controls: dropdowns, checkboxes, sliders, line edits
- Save and reset functionality
- Real-time validation
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QHBoxLayout, QComboBox,
    QCheckBox, QSpinBox, QDoubleSpinBox, QPushButton,
    QLineEdit, QSlider, QLabel, QGroupBox, QScrollArea,
    QMessageBox, QGridLayout, QFrame
)
from PySide6.QtCore import Signal, Qt, QEvent
import logging

from PySide6.QtGui import QStandardItemModel, QStandardItem, QColor, QBrush
from app.core.audio_capture import AudioRecorder
from app.core.whisper_engine import WhisperEngine

logger = logging.getLogger(__name__)


class SettingsPanel(QWidget):
    """
    Settings UI for all configuration options.
    Changes are saved to ConfigManager on Save button click.
    """

    # Signals
    settings_saved = Signal()  # Emitted when settings are saved
    model_changed = Signal(str)  # Emitted when Whisper model is changed

    def __init__(self, config_manager):
        """
        Initialize settings panel

        Args:
            config_manager: ConfigManager instance
        """
        super().__init__()
        self.config = config_manager

        # Store widgets for validation
        self.widgets = {}
        self.setting_groups = [] # Store group widgets for grid layout

        self._setup_ui()
        self._load_settings()
        
        # Install event filter for resize
        self.installEventFilter(self)

        logger.info("SettingsPanel initialized")

    def _setup_ui(self):
        """
        Create settings sections:
        - Whisper Model
        - Audio
        - Hotkey
        - Overlay
        - Advanced
        """
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Header
        header_label = QLabel("Settings")
        header_label.setStyleSheet("font-size: 24px; font-weight: bold; color: #ffffff;")
        layout.addWidget(header_label)

        # Scrollable area for settings
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll.setStyleSheet("""
            QScrollArea { background-color: transparent; border: none; }
            QScrollBar:vertical {
                background: #2d2d2d;
                width: 10px;
                margin: 0px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical {
                background: #4d4d4d;
                min-height: 20px;
                border-radius: 5px;
            }
        """)

        self.scroll_content = QWidget()
        self.scroll_content.setStyleSheet("background-color: transparent;")
        
        # Grid layout for groups
        self.grid_layout = QGridLayout(self.scroll_content)
        self.grid_layout.setSpacing(16)
        self.grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Create setting groups and add to list
        self.setting_groups.append(self._create_whisper_group())
        self.setting_groups.append(self._create_audio_group())
        self.setting_groups.append(self._create_hotkey_group())
        self.setting_groups.append(self._create_overlay_group())
        self.setting_groups.append(self._create_advanced_group())
        
        # Initial layout
        self._reflow_grid()

        self.scroll.setWidget(self.scroll_content)
        layout.addWidget(self.scroll, 1)

        # Action buttons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(8)

        save_btn = QPushButton("Save Settings")
        save_btn.clicked.connect(self.save_settings)
        save_btn.setStyleSheet(self._primary_button_style())

        reset_btn = QPushButton("Reset to Defaults")
        reset_btn.clicked.connect(self.reset_to_defaults)
        reset_btn.setStyleSheet(self._button_style())

        button_layout.addStretch()
        button_layout.addWidget(reset_btn)
        button_layout.addWidget(save_btn)

        layout.addLayout(button_layout)

    def _create_whisper_group(self) -> QGroupBox:
        """Create Whisper Model settings group"""
        group = QGroupBox("Whisper Model")
        group.setStyleSheet(self._group_style())

        form = QFormLayout(group)
        form.setSpacing(12)
        form.setContentsMargins(16, 24, 16, 16)

        # Get available VRAM
        available_vram = WhisperEngine.get_available_vram()
        
        # Model dropdown with VRAM validation
        model_combo = QComboBox()
        self.widgets['whisper.model'] = model_combo
        
        # Use StandardItemModel to support disabling items
        model_item_model = QStandardItemModel()
        
        for model_name in WhisperEngine.VALID_MODELS:
            req_vram = WhisperEngine.MODEL_VRAM_REQS.get(model_name, 0)
            item = QStandardItem(model_name)
            
            # Disable if insufficient VRAM (with 0.5 GB buffer)
            if available_vram > 0 and req_vram > (available_vram + 0.5):
                item.setEnabled(False)
                item.setForeground(QBrush(QColor("#666666")))
                item.setToolTip(f"Requires ~{req_vram} GB VRAM (Available: {available_vram:.1f} GB)")
            else:
                item.setToolTip(f"Estimated VRAM: ~{req_vram} GB")
                
            model_item_model.appendRow(item)
            
        model_combo.setModel(model_item_model)
        model_combo.setStyleSheet(self._combo_style())
        model_combo.currentTextChanged.connect(self._on_model_selection_changed)
        
        form.addRow("Model:", model_combo)

        # Language dropdown
        lang_combo = QComboBox()
        languages = [
            ('Auto-detect', None),
            ('English', 'en'),
            ('Spanish', 'es'),
            ('French', 'fr'),
            ('German', 'de'),
            ('Italian', 'it'),
            ('Portuguese', 'pt'),
            ('Dutch', 'nl'),
            ('Russian', 'ru'),
            ('Chinese', 'zh'),
            ('Japanese', 'ja'),
            ('Korean', 'ko'),
            ('Tamil', 'ta')
        ]
        for name, code in languages:
            lang_combo.addItem(name, code)
        lang_combo.setStyleSheet(self._combo_style())
        self.widgets['whisper.language'] = lang_combo
        form.addRow("Language:", lang_combo)

        # Device (read-only for now)
        device_label = QLabel()
        device_label.setStyleSheet("color: #cccccc;")
        self.widgets['whisper.device_label'] = device_label
        form.addRow("Device:", device_label)

        # VRAM Usage Info
        self.vram_estimates_label = QLabel("")
        self.vram_estimates_label.setStyleSheet("color: #aaaaaa; font-style: italic;")
        form.addRow("", self.vram_estimates_label)

        # Actual VRAM usage label (updated externally)
        vram_label = QLabel("N/A")
        vram_label.setStyleSheet("color: #888888;")
        self.widgets['vram_label'] = vram_label
        form.addRow("Actual VRAM:", vram_label)

        return group

    def _create_audio_group(self) -> QGroupBox:
        """Create Audio settings group"""
        group = QGroupBox("Audio")
        group.setStyleSheet(self._group_style())

        form = QFormLayout(group)
        form.setSpacing(12)
        form.setContentsMargins(16, 24, 16, 16)

        # Device selector
        device_combo = QComboBox()
        device_combo.setStyleSheet(self._combo_style())
        try:
            devices = AudioRecorder.list_devices()
            device_combo.addItem("Default Microphone", None)
            for dev in devices:
                device_combo.addItem(
                    f"{dev['name']} ({dev['sample_rate']}Hz)",
                    dev['index']
                )
        except Exception as e:
            logger.error(f"Failed to list audio devices: {e}")
            device_combo.addItem("Error loading devices", None)

        self.widgets['audio.device'] = device_combo
        form.addRow("Device:", device_combo)

        # Test button
        test_btn = QPushButton("Test Recording (2s)")
        test_btn.clicked.connect(self._test_recording)
        test_btn.setStyleSheet(self._button_style())
        form.addRow("", test_btn)

        # Noise reduction checkbox
        noise_cb = QCheckBox("Enable noise reduction")
        noise_cb.setStyleSheet("color: #cccccc;")
        self.widgets['audio.noise_reduction'] = noise_cb
        form.addRow("", noise_cb)

        # VAD checkbox
        vad_cb = QCheckBox("Enable Voice Activity Detection")
        vad_cb.setStyleSheet("color: #cccccc;")
        self.widgets['audio.vad_enabled'] = vad_cb
        form.addRow("", vad_cb)

        return group

    def _create_hotkey_group(self) -> QGroupBox:
        """Create Hotkey settings group"""
        group = QGroupBox("Hotkey")
        group.setStyleSheet(self._group_style())

        form = QFormLayout(group)
        form.setSpacing(12)
        form.setContentsMargins(16, 24, 16, 16)

        # Primary hotkey
        primary_layout = QHBoxLayout()
        primary_edit = QLineEdit()
        primary_edit.setPlaceholderText("e.g., ctrl+space")
        primary_edit.setStyleSheet(self._lineedit_style())
        self.widgets['hotkey.primary'] = primary_edit

        primary_test_btn = QPushButton("Test")
        primary_test_btn.setFixedWidth(70)
        primary_test_btn.clicked.connect(lambda: self._test_hotkey('primary'))
        primary_test_btn.setStyleSheet(self._button_style())

        primary_layout.addWidget(primary_edit, 1)
        primary_layout.addWidget(primary_test_btn)
        form.addRow("Primary:", primary_layout)

        # Fallback hotkey
        fallback_layout = QHBoxLayout()
        fallback_edit = QLineEdit()
        fallback_edit.setPlaceholderText("e.g., ctrl+shift+v")
        fallback_edit.setStyleSheet(self._lineedit_style())
        self.widgets['hotkey.fallback'] = fallback_edit

        fallback_test_btn = QPushButton("Test")
        fallback_test_btn.setFixedWidth(70)
        fallback_test_btn.clicked.connect(lambda: self._test_hotkey('fallback'))
        fallback_test_btn.setStyleSheet(self._button_style())

        fallback_layout.addWidget(fallback_edit, 1)
        fallback_layout.addWidget(fallback_test_btn)
        form.addRow("Fallback:", fallback_layout)

        # Reset button
        reset_btn = QPushButton("Reset to Default")
        reset_btn.clicked.connect(self._reset_hotkeys)
        reset_btn.setStyleSheet(self._button_style())
        form.addRow("", reset_btn)

        return group

    def _create_overlay_group(self) -> QGroupBox:
        """Create Overlay settings group"""
        group = QGroupBox("Overlay")
        group.setStyleSheet(self._group_style())

        form = QFormLayout(group)
        form.setSpacing(12)
        form.setContentsMargins(16, 24, 16, 16)

        # Enabled checkbox
        enabled_cb = QCheckBox("Enable overlay")
        enabled_cb.setStyleSheet("color: #cccccc;")
        self.widgets['overlay.enabled'] = enabled_cb
        form.addRow("", enabled_cb)

        # Position dropdown
        position_combo = QComboBox()
        position_combo.addItems(['top-center', 'top-left', 'top-right', 'bottom-center'])
        position_combo.setStyleSheet(self._combo_style())
        self.widgets['overlay.position'] = position_combo
        form.addRow("Position:", position_combo)

        # Monitor dropdown
        monitor_combo = QComboBox()
        monitor_combo.addItems(['Primary (0)', 'Secondary (1)', 'Tertiary (2)'])
        monitor_combo.setStyleSheet(self._combo_style())
        self.widgets['overlay.monitor'] = monitor_combo
        form.addRow("Monitor:", monitor_combo)

        # Auto-dismiss slider
        dismiss_layout = QVBoxLayout()
        dismiss_slider = QSlider(Qt.Orientation.Horizontal)
        dismiss_slider.setRange(1000, 5000)
        dismiss_slider.setSingleStep(100)
        dismiss_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        dismiss_slider.setTickInterval(1000)
        dismiss_slider.setStyleSheet(self._slider_style())

        dismiss_label = QLabel("2500 ms")
        dismiss_label.setStyleSheet("color: #888888; font-size: 12px;")
        dismiss_slider.valueChanged.connect(
            lambda v: dismiss_label.setText(f"{v} ms")
        )

        dismiss_layout.addWidget(dismiss_slider)
        dismiss_layout.addWidget(dismiss_label)

        self.widgets['overlay.auto_dismiss_ms'] = dismiss_slider
        form.addRow("Auto-dismiss:", dismiss_layout)

        return group

    def _create_advanced_group(self) -> QGroupBox:
        """Create Advanced settings group"""
        group = QGroupBox("Advanced")
        group.setStyleSheet(self._group_style())

        form = QFormLayout(group)
        form.setSpacing(12)
        form.setContentsMargins(16, 24, 16, 16)

        # fp16 checkbox
        fp16_cb = QCheckBox("fp16 (GPU optimization)")
        fp16_cb.setStyleSheet("color: #cccccc;")
        self.widgets['whisper.fp16'] = fp16_cb
        form.addRow("", fp16_cb)

        # Beam size
        beam_spin = QSpinBox()
        beam_spin.setRange(1, 5)
        beam_spin.setValue(1)
        beam_spin.setStyleSheet(self._spinbox_style())
        beam_spin.setToolTip("Number of alternative paths to search. Higher = better accuracy but slower.")
        self.widgets['whisper.beam_size'] = beam_spin
        form.addRow("Beam size:", beam_spin)

        # Temperature
        temp_spin = QDoubleSpinBox()
        temp_spin.setRange(0.0, 1.0)
        temp_spin.setSingleStep(0.1)
        temp_spin.setDecimals(1)
        temp_spin.setValue(0.0)
        temp_spin.setStyleSheet(self._spinbox_style())
        temp_spin.setToolTip("Higher values = more creative/random. Lower = more deterministic.")
        self.widgets['whisper.temperature'] = temp_spin
        form.addRow("Temperature:", temp_spin)

        # History retention
        retention_spin = QSpinBox()
        retention_spin.setRange(0, 365)
        retention_spin.setValue(30)
        retention_spin.setSpecialValueText("Unlimited")
        retention_spin.setSuffix(" days")
        retention_spin.setStyleSheet(self._spinbox_style())
        self.widgets['storage.retention_days'] = retention_spin
        form.addRow("History retention:", retention_spin)

        return group

    def _load_settings(self):
        """Load current settings from ConfigManager into UI controls"""
        try:
            # Whisper
            model = self.config.get('whisper.model', 'small')
            self.widgets['whisper.model'].setCurrentText(model)

            language = self.config.get('whisper.language')
            lang_combo = self.widgets['whisper.language']
            for i in range(lang_combo.count()):
                if lang_combo.itemData(i) == language:
                    lang_combo.setCurrentIndex(i)
                    break

            device = self.config.get('whisper.device', 'cuda')
            self.widgets['whisper.device_label'].setText(device.upper())

            # Audio
            audio_device = self.config.get('audio.device')
            device_combo = self.widgets['audio.device']
            if audio_device is None:
                device_combo.setCurrentIndex(0)
            else:
                for i in range(device_combo.count()):
                    if device_combo.itemData(i) == audio_device:
                        device_combo.setCurrentIndex(i)
                        break

            self.widgets['audio.noise_reduction'].setChecked(
                self.config.get('audio.noise_reduction', False)
            )
            self.widgets['audio.vad_enabled'].setChecked(
                self.config.get('audio.vad_enabled', False)
            )

            # Hotkey
            self.widgets['hotkey.primary'].setText(
                self.config.get('hotkey.primary', 'ctrl+space')
            )
            self.widgets['hotkey.fallback'].setText(
                self.config.get('hotkey.fallback', 'ctrl+shift+v')
            )

            # Overlay
            self.widgets['overlay.enabled'].setChecked(
                self.config.get('overlay.enabled', True)
            )
            self.widgets['overlay.position'].setCurrentText(
                self.config.get('overlay.position', 'top-center')
            )
            self.widgets['overlay.monitor'].setCurrentIndex(
                self.config.get('overlay.monitor', 0)
            )
            self.widgets['overlay.auto_dismiss_ms'].setValue(
                self.config.get('overlay.auto_dismiss_ms', 2500)
            )

            # Advanced
            self.widgets['whisper.fp16'].setChecked(
                self.config.get('whisper.fp16', True)
            )
            self.widgets['whisper.beam_size'].setValue(
                self.config.get('whisper.beam_size', 1)
            )
            self.widgets['whisper.temperature'].setValue(
                self.config.get('whisper.temperature', 0.0)
            )
            self.widgets['storage.retention_days'].setValue(
                self.config.get('storage.retention_days', 30)
            )

            logger.info("Settings loaded into UI")

        except Exception as e:
            logger.error(f"Failed to load settings: {e}")

    def save_settings(self):
        """
        Save all settings to ConfigManager and emit signal
        Validates inputs before saving.
        Shows success message on save.
        """
        try:
            # Validate first
            is_valid, error_msg = self.validate_settings()
            if not is_valid:
                QMessageBox.warning(
                    self,
                    "Validation Error",
                    f"Invalid settings:\n{error_msg}"
                )
                return

            # Save Whisper settings
            self.config.set('whisper.model', self.widgets['whisper.model'].currentText())

            lang_combo = self.widgets['whisper.language']
            language = lang_combo.currentData()
            self.config.set('whisper.language', language)

            # Audio settings
            device_combo = self.widgets['audio.device']
            audio_device = device_combo.currentData()
            self.config.set('audio.device', audio_device)

            self.config.set('audio.noise_reduction',
                          self.widgets['audio.noise_reduction'].isChecked())
            self.config.set('audio.vad_enabled',
                          self.widgets['audio.vad_enabled'].isChecked())

            # Hotkey settings
            self.config.set('hotkey.primary',
                          self.widgets['hotkey.primary'].text().strip())
            self.config.set('hotkey.fallback',
                          self.widgets['hotkey.fallback'].text().strip())

            # Overlay settings
            self.config.set('overlay.enabled',
                          self.widgets['overlay.enabled'].isChecked())
            self.config.set('overlay.position',
                          self.widgets['overlay.position'].currentText())
            self.config.set('overlay.monitor',
                          self.widgets['overlay.monitor'].currentIndex())
            self.config.set('overlay.auto_dismiss_ms',
                          self.widgets['overlay.auto_dismiss_ms'].value())

            # Advanced settings
            self.config.set('whisper.fp16',
                          self.widgets['whisper.fp16'].isChecked())
            self.config.set('whisper.beam_size',
                          self.widgets['whisper.beam_size'].value())
            self.config.set('whisper.temperature',
                          self.widgets['whisper.temperature'].value())
            self.config.set('storage.retention_days',
                          self.widgets['storage.retention_days'].value())

            # Save to file
            self.config.save()

            # Emit signal
            self.settings_saved.emit()

            logger.info("Settings saved successfully")

            QMessageBox.information(
                self,
                "Settings Saved",
                "Settings have been saved successfully!"
            )

        except Exception as e:
            logger.error(f"Failed to save settings: {e}")
            QMessageBox.critical(
                self,
                "Save Failed",
                f"Failed to save settings:\n{str(e)}"
            )

    def reset_to_defaults(self):
        """
        Reset all settings to default values
        Shows confirmation dialog before resetting.
        """
        reply = QMessageBox.question(
            self,
            "Reset Settings",
            "Are you sure you want to reset all settings to defaults?\n"
            "This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                self.config.reset_to_defaults()
                self.config.save()
                self._load_settings()

                logger.info("Settings reset to defaults")

                QMessageBox.information(
                    self,
                    "Reset Complete",
                    "Settings have been reset to defaults."
                )

            except Exception as e:
                logger.error(f"Failed to reset settings: {e}")
                QMessageBox.critical(
                    self,
                    "Reset Failed",
                    f"Failed to reset settings:\n{str(e)}"
                )

    def validate_settings(self) -> tuple[bool, str]:
        """
        Validate all settings

        Returns:
            (is_valid, error_message) tuple
        """
        errors = []

        # Validate hotkeys
        primary = self.widgets['hotkey.primary'].text().strip()
        if not primary:
            errors.append("Primary hotkey cannot be empty")
        elif '+' not in primary:
            errors.append("Primary hotkey must include modifier (e.g., ctrl+space)")

        fallback = self.widgets['hotkey.fallback'].text().strip()
        if not fallback:
            errors.append("Fallback hotkey cannot be empty")
        elif '+' not in fallback:
            errors.append("Fallback hotkey must include modifier")

        if primary.lower() == fallback.lower():
            errors.append("Primary and fallback hotkeys must be different")

        # Validate numeric ranges
        beam_size = self.widgets['whisper.beam_size'].value()
        if beam_size < 1 or beam_size > 5:
            errors.append("Beam size must be between 1 and 5")

        temp = self.widgets['whisper.temperature'].value()
        if temp < 0.0 or temp > 1.0:
            errors.append("Temperature must be between 0.0 and 1.0")

        if errors:
            return False, "\n".join(errors)

        return True, ""

    def _on_model_selection_changed(self, model_name: str):
        """Update UI based on selected model"""
        # Emit change signal
        self.model_changed.emit(model_name)
        
        # Update estimate label
        req_vram = WhisperEngine.MODEL_VRAM_REQS.get(model_name, 0)
        self.vram_estimates_label.setText(f"Estimated Checkpoint Size: ~{req_vram} GB")

    def _test_recording(self):
        """Test audio recording for 2 seconds"""
        try:
            QMessageBox.information(
                self,
                "Test Recording",
                "Test recording will be implemented with WhisperEngine integration.\n"
                "This would record 2 seconds and show a waveform preview."
            )
        except Exception as e:
            logger.error(f"Test recording failed: {e}")

    def _test_hotkey(self, which: str):
        """Test hotkey detection"""
        hotkey = self.widgets[f'hotkey.{which}'].text()
        QMessageBox.information(
            self,
            "Hotkey Test",
            f"Testing {which} hotkey: {hotkey}\n\n"
            "Press the hotkey to test...\n"
            "(Full implementation requires HotkeyManager integration)"
        )

    def eventFilter(self, obj, event):
        """Handle resize events to reflow grid"""
        if obj == self and event.type() == QEvent.Type.Resize:
            self._reflow_grid()
        return super().eventFilter(obj, event)

    def _reflow_grid(self):
        """
        Reflow groups into grid.
        Fixed layout: 2 columns.
        """
        # Clear layout
        while self.grid_layout.count():
            self.grid_layout.takeAt(0)
            
        cols = 1
            
        for i, widget in enumerate(self.setting_groups):
            row = i // cols
            col = i % cols
            self.grid_layout.addWidget(widget, row, col)
            
        # Set stretch
        for c in range(cols):
            self.grid_layout.setColumnStretch(c, 1)

    # Stylesheet methods
    def _reset_hotkeys(self):
        """Reset hotkeys to default values"""
        self.widgets['hotkey.primary'].setText('ctrl+space')
        self.widgets['hotkey.fallback'].setText('ctrl+shift+v')

    # Stylesheet methods
    def _group_style(self) -> str:
        """GroupBox stylesheet"""
        return """
            QGroupBox {
                border: 1px solid #3d3d3d;
                border-radius: 8px;
                margin-top: 12px;
                padding: 12px;
                font-weight: bold;
                color: #ffffff;
                background-color: #252525;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 8px;
                background-color: transparent;
            }
        """

    def _combo_style(self) -> str:
        """ComboBox stylesheet"""
        return """
            QComboBox {
                background-color: #2d2d2d;
                border: 1px solid #3d3d3d;
                border-radius: 4px;
                padding: 6px 10px;
                color: #ffffff;
                min-width: 200px;
            }
            QComboBox:hover {
                border-color: #0078d4;
            }
            QComboBox::drop-down {
                border: none;
                padding-right: 8px;
            }
            QComboBox QAbstractItemView {
                background-color: #2d2d2d;
                border: 1px solid #3d3d3d;
                selection-background-color: #0078d4;
                color: #ffffff;
            }
        """

    def _lineedit_style(self) -> str:
        """LineEdit stylesheet"""
        return """
            QLineEdit {
                background-color: #2d2d2d;
                border: 1px solid #3d3d3d;
                border-radius: 4px;
                padding: 6px 10px;
                color: #ffffff;
            }
            QLineEdit:focus {
                border-color: #0078d4;
            }
        """

    def _button_style(self) -> str:
        """Button stylesheet"""
        return """
            QPushButton {
                background-color: #2d2d2d;
                border: 1px solid #3d3d3d;
                border-radius: 4px;
                padding: 8px 16px;
                color: #ffffff;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #3d3d3d;
                border-color: #4d4d4d;
            }
            QPushButton:pressed {
                background-color: #4d4d4d;
            }
        """

    def _primary_button_style(self) -> str:
        """Primary button stylesheet"""
        return """
            QPushButton {
                background-color: #0078d4;
                border: 1px solid #0078d4;
                border-radius: 4px;
                padding: 10px 24px;
                color: #ffffff;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #005a9e;
                border-color: #005a9e;
            }
            QPushButton:pressed {
                background-color: #004578;
            }
        """

    def _spinbox_style(self) -> str:
        """SpinBox stylesheet"""
        return """
            QSpinBox, QDoubleSpinBox {
                background-color: #2d2d2d;
                border: 1px solid #3d3d3d;
                border-radius: 4px;
                padding: 6px 10px;
                color: #ffffff;
            }
            QSpinBox:hover, QDoubleSpinBox:hover {
                border-color: #0078d4;
            }
        """

    def _slider_style(self) -> str:
        """Slider stylesheet"""
        return """
            QSlider::groove:horizontal {
                background: #3d3d3d;
                height: 6px;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #0078d4;
                width: 16px;
                height: 16px;
                margin: -5px 0;
                border-radius: 8px;
            }
            QSlider::handle:horizontal:hover {
                background: #005a9e;
            }
        """
