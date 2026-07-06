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
import sys

from PySide6.QtGui import QStandardItemModel, QStandardItem, QColor, QBrush
from app.core.audio_capture import AudioRecorder
from app.core.whisper_engine import (
    WhisperEngine, valid_models, model_memory_reqs, get_engine_class,
)
from app.ui.widgets import ModernCheckBox

logger = logging.getLogger(__name__)


class SettingsPanel(QWidget):
    """
    Settings UI for all configuration options.
    Changes are saved to ConfigManager on Save button click.
    """

    # Signals
    settings_saved = Signal()  # Emitted when settings are saved
    model_changed = Signal(str)  # Emitted when Whisper model is changed
    rerun_setup_requested = Signal()  # Emitted on darwin when user clicks "Re-run setup…"

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
        from app.ui.theme import TEXT

        layout = QVBoxLayout(self)
        # Tighter outer margins so the 2-column grid fits comfortably in
        # the 880-px default window (sidebar takes 150 px, leaving ~730).
        layout.setContentsMargins(14, 16, 14, 14)
        layout.setSpacing(16)

        # Header
        header_label = QLabel("Settings")
        header_label.setStyleSheet(f"font-size: 22px; font-weight: 700; color: {TEXT};")
        layout.addWidget(header_label)

        # Scrollable area for settings — vertical only, never horizontal.
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll.setStyleSheet(
            "QScrollArea { background-color: transparent; border: none; }"
        )

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
        if sys.platform == 'darwin':
            self.setting_groups.append(self._create_macos_group())
        if sys.platform == 'win32':
            self.setting_groups.append(self._create_windows_group())
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

        # On macOS, expose a "Re-run setup…" button so the user can
        # re-trigger the onboarding wizard if they skipped or denied
        # permissions on first launch.
        if sys.platform == 'darwin':
            rerun_btn = QPushButton("Re-run setup…")
            rerun_btn.clicked.connect(self.rerun_setup_requested.emit)
            rerun_btn.setStyleSheet(self._button_style())
            button_layout.addWidget(rerun_btn)

        button_layout.addStretch()
        button_layout.addWidget(reset_btn)
        button_layout.addWidget(save_btn)

        layout.addLayout(button_layout)

    def _create_whisper_group(self) -> QGroupBox:
        """Create Whisper Model settings group"""
        group = QGroupBox("Whisper Model")
        group.setStyleSheet(self._group_style())

        form = QFormLayout(group)
        form.setSpacing(8)
        form.setContentsMargins(0, 0, 0, 0)

        # Get available memory (VRAM on Linux/NVIDIA, unified on Apple Silicon)
        available_vram = get_engine_class().get_available_vram()
        memory_table = model_memory_reqs()

        # Model dropdown — populated from the actual platform's engine so
        # the choices match what can actually be loaded (MLX on macOS
        # supports a slightly different set than torch on Linux).
        model_combo = QComboBox()
        self.widgets['whisper.model'] = model_combo

        # Use StandardItemModel to support disabling items
        model_item_model = QStandardItemModel()

        for model_name in valid_models():
            req_vram = memory_table.get(model_name, 0)
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

        # Actual VRAM usage label (updated externally). On macOS, MLX uses
        # unified memory; the label text reflects that.
        vram_label = QLabel("N/A")
        vram_label.setStyleSheet("color: #888888;")
        self.widgets['vram_label'] = vram_label
        vram_row_label = "Unified memory:" if sys.platform == 'darwin' else "Actual VRAM:"
        form.addRow(vram_row_label, vram_label)

        return group

    def _create_audio_group(self) -> QGroupBox:
        """Create Audio settings group"""
        group = QGroupBox("Audio")
        group.setStyleSheet(self._group_style())

        form = QFormLayout(group)
        form.setSpacing(8)
        form.setContentsMargins(0, 0, 0, 0)

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
        test_btn = QPushButton("Test Mic")
        test_btn.clicked.connect(self._test_recording)
        test_btn.setStyleSheet(self._button_style())
        form.addRow("", test_btn)

        # Noise reduction checkbox
        noise_cb = ModernCheckBox("Enable noise reduction")
        noise_cb.setStyleSheet("color: #cccccc;")
        self.widgets['audio.noise_reduction'] = noise_cb
        form.addRow("", noise_cb)

        # VAD checkbox
        vad_cb = ModernCheckBox("Enable Voice Activity Detection")
        vad_cb.setStyleSheet("color: #cccccc;")
        self.widgets['audio.vad_enabled'] = vad_cb
        form.addRow("", vad_cb)

        return group

    def _create_hotkey_group(self) -> QGroupBox:
        """Create Hotkey settings group"""
        group = QGroupBox("Hotkey")
        group.setStyleSheet(self._group_style())

        form = QFormLayout(group)
        form.setSpacing(8)
        form.setContentsMargins(0, 0, 0, 0)

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
        form.setSpacing(8)
        form.setContentsMargins(0, 0, 0, 0)

        # Enabled checkbox
        enabled_cb = ModernCheckBox("Enable overlay")
        enabled_cb.setStyleSheet("color: #cccccc;")
        self.widgets['overlay.enabled'] = enabled_cb
        form.addRow("", enabled_cb)

        # Position dropdown
        position_combo = QComboBox()
        position_combo.addItems(['top-center', 'top-left', 'top-right', 'bottom-center', 'bottom-left', 'bottom-right'])
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

    def _create_macos_group(self) -> QGroupBox:
        """Create the macOS-only settings group.

        Houses Mac-native polish toggles. Both toggles apply *immediately*
        (not on Save) since their effects are immediately visible.
        """
        group = QGroupBox("macOS")
        group.setStyleSheet(self._group_style())

        form = QFormLayout(group)
        form.setSpacing(8)
        form.setContentsMargins(0, 0, 0, 0)

        # Open at Login — uses SMAppService (macOS 13+).
        open_at_login_cb = ModernCheckBox("Open Whisper-Free at login")
        open_at_login_cb.setStyleSheet("color: #cccccc;")
        open_at_login_cb.setToolTip(
            "Start Whisper-Free automatically when you log in. "
            "May not work when running from source — only the bundled "
            ".app installed to /Applications can register reliably."
        )
        open_at_login_cb.stateChanged.connect(self._on_open_at_login_toggled)
        self.widgets['macos.open_at_login'] = open_at_login_cb
        form.addRow("", open_at_login_cb)

        # Show in Dock — toggles NSApp activation policy live.
        show_in_dock_cb = ModernCheckBox("Show Whisper-Free in the Dock")
        show_in_dock_cb.setStyleSheet("color: #cccccc;")
        show_in_dock_cb.setToolTip(
            "By default Whisper-Free is a menu-bar agent (no Dock icon). "
            "Enable this to also show it in the Dock. Takes effect immediately."
        )
        show_in_dock_cb.stateChanged.connect(self._on_show_in_dock_toggled)
        self.widgets['macos.show_in_dock'] = show_in_dock_cb
        form.addRow("", show_in_dock_cb)

        return group

    def _on_open_at_login_toggled(self, state) -> None:
        """Apply + persist Open-at-Login immediately."""
        from PySide6.QtCore import Qt as _Qt
        enabled = (state == _Qt.CheckState.Checked.value) or (state == _Qt.Checked)
        try:
            from app.platform import autolaunch
            ok = autolaunch.set_open_at_login(enabled)
            if not ok:
                logger.warning(
                    f"Open at Login {'enable' if enabled else 'disable'} failed. "
                    "When running from source this is expected; the bundled "
                    ".app installed to /Applications will work."
                )
        except Exception as e:
            logger.error(f"Open at Login toggle failed: {e}")
        try:
            self.config.set('macos.open_at_login', enabled)
            self.config.save()
        except Exception as e:
            logger.error(f"Could not persist macos.open_at_login: {e}")

    def _on_show_in_dock_toggled(self, state) -> None:
        """Apply + persist Show-in-Dock immediately."""
        from PySide6.QtCore import Qt as _Qt
        visible = (state == _Qt.CheckState.Checked.value) or (state == _Qt.Checked)
        try:
            from app.platform import set_dock_visible
            set_dock_visible(visible)
        except Exception as e:
            logger.error(f"Show in Dock toggle failed: {e}")
        try:
            self.config.set('macos.show_in_dock', visible)
            self.config.save()
        except Exception as e:
            logger.error(f"Could not persist macos.show_in_dock: {e}")

    def _create_windows_group(self) -> QGroupBox:
        """Create the Windows-only settings group.

        Applies immediately (not on Save) since its effect (registry Run
        key) is immediately in force, matching the macOS toggle pattern.
        """
        group = QGroupBox("Windows")
        group.setStyleSheet(self._group_style())

        form = QFormLayout(group)
        form.setSpacing(8)
        form.setContentsMargins(0, 0, 0, 0)

        open_at_login_cb = ModernCheckBox("Open Whisper-Free at login")
        open_at_login_cb.setStyleSheet("color: #cccccc;")
        open_at_login_cb.setToolTip(
            "Start Whisper-Free automatically when you sign in to Windows."
        )
        open_at_login_cb.stateChanged.connect(self._on_windows_open_at_login_toggled)
        self.widgets['windows.open_at_login'] = open_at_login_cb
        form.addRow("", open_at_login_cb)

        return group

    def _on_windows_open_at_login_toggled(self, state) -> None:
        """Apply + persist Open-at-Login immediately."""
        from PySide6.QtCore import Qt as _Qt
        enabled = (state == _Qt.CheckState.Checked.value) or (state == _Qt.Checked)
        try:
            from app.platform import autolaunch
            ok = autolaunch.set_open_at_login(enabled)
            if not ok:
                logger.warning(
                    f"Open at Login {'enable' if enabled else 'disable'} failed."
                )
        except Exception as e:
            logger.error(f"Open at Login toggle failed: {e}")
        try:
            self.config.set('windows.open_at_login', enabled)
            self.config.save()
        except Exception as e:
            logger.error(f"Could not persist windows.open_at_login: {e}")

    def _create_advanced_group(self) -> QGroupBox:
        """Create Advanced settings group"""
        group = QGroupBox("Advanced")
        group.setStyleSheet(self._group_style())

        form = QFormLayout(group)
        form.setSpacing(8)
        form.setContentsMargins(0, 0, 0, 0)

        # fp16 checkbox. On macOS the MLX backend manages precision internally,
        # so this setting is irrelevant — we keep the widget for cross-platform
        # config parity but disable it with an explanatory tooltip.
        fp16_cb = ModernCheckBox("fp16 (GPU optimization)")
        fp16_cb.setStyleSheet("color: #cccccc;")
        if sys.platform == 'darwin':
            fp16_cb.setEnabled(False)
            fp16_cb.setToolTip(
                "Not applicable on macOS — MLX manages precision automatically."
            )
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

            # Device label — platform-aware. On macOS the engine is always
            # MLX on Apple Silicon regardless of what the config says
            # (`device` is a Linux-era key that defaults to 'cuda').
            if sys.platform == 'darwin':
                device_text = "Apple Silicon (MLX)"
            else:
                device_text = self.config.get('whisper.device', 'cuda').upper()
            self.widgets['whisper.device_label'].setText(device_text)

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

            # macOS (only created on darwin)
            if sys.platform == 'darwin':
                # Block signals while we sync from config so the stateChanged
                # handlers don't re-fire side effects (autolaunch register,
                # setActivationPolicy) just from loading saved state.
                for key in ('macos.open_at_login', 'macos.show_in_dock'):
                    cb = self.widgets.get(key)
                    if cb is not None:
                        cb.blockSignals(True)
                        cb.setChecked(self.config.get(key, False))
                        cb.blockSignals(False)

            # Windows (only created on win32)
            if sys.platform == 'win32':
                cb = self.widgets.get('windows.open_at_login')
                if cb is not None:
                    cb.blockSignals(True)
                    cb.setChecked(self.config.get('windows.open_at_login', False))
                    cb.blockSignals(False)

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

    def update_vram_usage(self, usage_mb: float) -> None:
        """Update the live memory display in the Whisper Model card.

        Called from MainWindow.update_vram_usage so the Settings panel
        stays in sync with whatever the status bar shows.
        """
        widget = self.widgets.get('vram_label')
        if widget is None:
            return
        if usage_mb >= 1024:
            widget.setText(f"{usage_mb / 1024:.2f} GB")
        else:
            widget.setText(f"{usage_mb:.0f} MB")

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
        
        # Update estimate label — uses the current platform's engine reqs.
        req_vram = model_memory_reqs().get(model_name, 0)
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
        """Reflow setting groups into a 2-column grid (3 rows on macOS).

        macOS layout:
            ┌─ Whisper Model ─┬─ Audio ───────┐
            ├─ Hotkey ────────┼─ Overlay ─────┤
            ├─ macOS ─────────┼─ Advanced ────┤
            └─────────────────┴───────────────┘

        Linux has 5 groups so the last cell stays empty — that's fine,
        the empty space sits in the bottom-right corner.
        """
        # Clear layout in place — takeAt(0) returns each item, we drop them.
        while self.grid_layout.count():
            self.grid_layout.takeAt(0)

        cols = 2
        for i, widget in enumerate(self.setting_groups):
            row = i // cols
            col = i % cols
            self.grid_layout.addWidget(widget, row, col)

        # Equal-width columns; allow rows to size to their content.
        for c in range(cols):
            self.grid_layout.setColumnStretch(c, 1)
        self.grid_layout.setHorizontalSpacing(16)
        self.grid_layout.setVerticalSpacing(16)

    # Stylesheet methods
    def _reset_hotkeys(self):
        """Reset hotkeys to default values"""
        self.widgets['hotkey.primary'].setText('ctrl+space')
        self.widgets['hotkey.fallback'].setText('ctrl+shift+v')

    # Style helpers — all delegate to the central theme module so visual
    # tokens live in one place. See app/ui/theme.py.
    def _group_style(self) -> str:
        from app.ui.theme import group_qss
        return group_qss()

    def _combo_style(self) -> str:
        from app.ui.theme import combo_qss
        return combo_qss()

    def _lineedit_style(self) -> str:
        from app.ui.theme import line_edit_qss
        return line_edit_qss()

    def _button_style(self) -> str:
        from app.ui.theme import secondary_button_qss
        return secondary_button_qss()

    def _primary_button_style(self) -> str:
        from app.ui.theme import primary_button_qss
        return primary_button_qss()

    def _spinbox_style(self) -> str:
        from app.ui.theme import spin_qss
        return spin_qss()

    def _slider_style(self) -> str:
        from app.ui.theme import slider_qss
        return slider_qss()
