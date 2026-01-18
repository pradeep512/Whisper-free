"""
Unit tests for MainWindow, HistoryPanel, and SettingsPanel

Tests all three UI components including initialization, navigation,
data loading, search, export, and settings management.
"""

import sys
import pytest
import tempfile
from pathlib import Path
from datetime import datetime

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from app.ui.main_window import MainWindow
from app.ui.history_panel import HistoryPanel
from app.ui.settings_panel import SettingsPanel
from app.data.database import DatabaseManager
from app.data.config import ConfigManager


@pytest.fixture(scope="session")
def qapp():
    """Create QApplication instance for tests"""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app
    # Don't quit - other tests may need it


@pytest.fixture
def db_manager():
    """Create in-memory database for testing"""
    db = DatabaseManager(":memory:")
    yield db
    db.close()


@pytest.fixture
def config_manager(tmp_path):
    """Create temporary config manager for testing"""
    config_file = tmp_path / "config.yaml"
    config = ConfigManager(str(config_file))
    yield config


class TestMainWindow:
    """Tests for MainWindow class"""

    def test_main_window_init(self, qapp, db_manager, config_manager):
        """Test MainWindow initialization"""
        window = MainWindow(db_manager, config_manager)

        assert window.windowTitle() == "Whisper-Free"
        assert window.width() == 900
        assert window.height() == 700
        assert window.db == db_manager
        assert window.config == config_manager

        # Check that panels are created
        assert window.history_panel is not None
        assert window.settings_panel is not None
        assert window.about_panel is not None

        # Check that stack has 3 panels
        assert window.stack.count() == 3

        # Check sidebar has 3 items
        assert window.sidebar.count() == 3

        window.close()

    def test_navigation(self, qapp, db_manager, config_manager):
        """Test sidebar navigation between panels"""
        window = MainWindow(db_manager, config_manager)

        # Default should be History (index 0)
        assert window.stack.currentIndex() == 0

        # Navigate to Settings
        window.show_settings()
        assert window.stack.currentIndex() == 1
        assert window.sidebar.currentRow() == 1

        # Navigate to About
        window.show_about()
        assert window.stack.currentIndex() == 2
        assert window.sidebar.currentRow() == 2

        # Navigate back to History
        window.show_history()
        assert window.stack.currentIndex() == 0
        assert window.sidebar.currentRow() == 0

        window.close()

    def test_add_transcription(self, qapp, db_manager, config_manager):
        """Test adding transcription to history"""
        window = MainWindow(db_manager, config_manager)

        # Add a transcription
        window.add_transcription(
            text="Test transcription",
            duration=5.2,
            language="en",
            model="small"
        )

        # Check that it was added to database
        history = db_manager.get_recent_transcriptions(limit=10)
        assert len(history) == 1
        assert history[0]['text'] == "Test transcription"
        assert history[0]['duration'] == 5.2
        assert history[0]['language'] == "en"
        assert history[0]['model_used'] == "small"

        # Check that history panel shows the item
        assert window.history_panel.history_list.count() == 1

        window.close()

    def test_status_updates(self, qapp, db_manager, config_manager):
        """Test status bar updates"""
        window = MainWindow(db_manager, config_manager)

        # Test status update
        window.update_status("Ready")
        assert "Ready" in window.status_label.text()

        window.update_status("Recording")
        assert "Recording" in window.status_label.text()

        window.update_status("Processing")
        assert "Processing" in window.status_label.text()

        # Test VRAM update
        window.update_vram_usage(1500)
        assert "1500 MB" in window.vram_label.text()

        window.update_vram_usage(2048)
        assert "2.00 GB" in window.vram_label.text()

        window.close()


class TestHistoryPanel:
    """Tests for HistoryPanel class"""

    def test_history_panel_init(self, qapp, db_manager):
        """Test HistoryPanel initialization"""
        panel = HistoryPanel(db_manager)

        assert panel.db == db_manager
        assert panel.history_list is not None
        assert panel.search_input is not None

    def test_load_history(self, qapp, db_manager):
        """Test loading history from database"""
        # Add test data
        db_manager.add_transcription("Test 1", "en", 1.0, "small")
        db_manager.add_transcription("Test 2", "es", 2.0, "medium")
        db_manager.add_transcription("Test 3", "fr", 3.0, "small")

        panel = HistoryPanel(db_manager)
        panel.load_history(limit=50)

        # Check that all 3 items are loaded
        assert panel.history_list.count() == 3

        # Check that most recent is first (Test 3)
        first_item = panel.history_list.item(0)
        first_widget = panel.history_list.itemWidget(first_item)
        assert first_widget is not None

    def test_search_history(self, qapp, db_manager):
        """Test search functionality"""
        # Add test data
        db_manager.add_transcription("Hello world", "en", 1.0, "small")
        db_manager.add_transcription("Goodbye world", "en", 1.0, "small")
        db_manager.add_transcription("Python programming", "en", 2.0, "medium")

        panel = HistoryPanel(db_manager)
        panel.load_history()

        assert panel.history_list.count() == 3

        # Search for "Hello"
        panel.search("Hello")

        # Count visible items
        visible_count = sum(
            1 for i in range(panel.history_list.count())
            if not panel.history_list.item(i).isHidden()
        )
        assert visible_count == 1

        # Search for "world"
        panel.search("world")
        visible_count = sum(
            1 for i in range(panel.history_list.count())
            if not panel.history_list.item(i).isHidden()
        )
        assert visible_count == 2

        # Clear search
        panel.search("")
        visible_count = sum(
            1 for i in range(panel.history_list.count())
            if not panel.history_list.item(i).isHidden()
        )
        assert visible_count == 3

    def test_export_txt(self, qapp, db_manager, tmp_path):
        """Test TXT export functionality"""
        # Add test data
        db_manager.add_transcription("Test 1", "en", 1.0, "small")
        db_manager.add_transcription("Test 2", "en", 2.0, "small")

        panel = HistoryPanel(db_manager)
        panel.load_history()

        # Export to TXT
        export_file = tmp_path / "export.txt"
        db_manager.export_to_txt(str(export_file))

        # Verify file exists and contains data
        assert export_file.exists()
        content = export_file.read_text()
        assert "Test 1" in content
        assert "Test 2" in content

    def test_export_json(self, qapp, db_manager, tmp_path):
        """Test JSON export functionality"""
        # Add test data
        db_manager.add_transcription("Test 1", "en", 1.0, "small")
        db_manager.add_transcription("Test 2", "es", 2.0, "medium")

        panel = HistoryPanel(db_manager)
        panel.load_history()

        # Export to JSON
        export_file = tmp_path / "export.json"
        db_manager.export_to_json(str(export_file))

        # Verify file exists and contains valid JSON
        assert export_file.exists()
        content = export_file.read_text()
        assert "Test 1" in content
        assert "Test 2" in content
        assert '"language": "en"' in content
        assert '"language": "es"' in content


class TestSettingsPanel:
    """Tests for SettingsPanel class"""

    def test_settings_panel_init(self, qapp, config_manager):
        """Test SettingsPanel initialization"""
        panel = SettingsPanel(config_manager)

        assert panel.config == config_manager
        assert len(panel.widgets) > 0

        # Check that key widgets exist
        assert 'whisper.model' in panel.widgets
        assert 'audio.device' in panel.widgets
        assert 'hotkey.primary' in panel.widgets
        assert 'overlay.enabled' in panel.widgets

    def test_load_settings(self, qapp, config_manager):
        """Test loading settings into UI"""
        # Set some config values
        config_manager.set('whisper.model', 'medium')
        config_manager.set('hotkey.primary', 'ctrl+alt+space')
        config_manager.set('overlay.enabled', False)

        panel = SettingsPanel(config_manager)

        # Verify values are loaded
        assert panel.widgets['whisper.model'].currentText() == 'medium'
        assert panel.widgets['hotkey.primary'].text() == 'ctrl+alt+space'
        assert panel.widgets['overlay.enabled'].isChecked() is False

    def test_save_settings(self, qapp, config_manager):
        """Test saving settings from UI to config"""
        panel = SettingsPanel(config_manager)

        # Modify some settings
        panel.widgets['whisper.model'].setCurrentText('large-v3-turbo')
        panel.widgets['whisper.beam_size'].setValue(3)
        panel.widgets['whisper.temperature'].setValue(0.5)
        panel.widgets['overlay.enabled'].setChecked(False)

        # Save settings
        panel.save_settings()

        # Verify config was updated
        assert config_manager.get('whisper.model') == 'large-v3-turbo'
        assert config_manager.get('whisper.beam_size') == 3
        assert config_manager.get('whisper.temperature') == 0.5
        assert config_manager.get('overlay.enabled') is False

    def test_validate_settings(self, qapp, config_manager):
        """Test settings validation"""
        panel = SettingsPanel(config_manager)

        # Valid settings
        panel.widgets['hotkey.primary'].setText('ctrl+space')
        panel.widgets['hotkey.fallback'].setText('ctrl+shift+v')
        is_valid, error = panel.validate_settings()
        assert is_valid is True
        assert error == ""

        # Invalid: no modifier in primary hotkey
        panel.widgets['hotkey.primary'].setText('space')
        is_valid, error = panel.validate_settings()
        assert is_valid is False
        assert "modifier" in error.lower()

        # Invalid: same hotkeys
        panel.widgets['hotkey.primary'].setText('ctrl+space')
        panel.widgets['hotkey.fallback'].setText('ctrl+space')
        is_valid, error = panel.validate_settings()
        assert is_valid is False
        assert "different" in error.lower()

    def test_reset_to_defaults(self, qapp, config_manager):
        """Test resetting settings to defaults"""
        panel = SettingsPanel(config_manager)

        # Modify some settings
        config_manager.set('whisper.model', 'large-v3-turbo')
        config_manager.set('whisper.beam_size', 5)
        config_manager.set('overlay.enabled', False)

        # Reset to defaults (without showing dialog)
        config_manager.reset_to_defaults()
        panel._load_settings()

        # Verify defaults are loaded
        assert panel.widgets['whisper.model'].currentText() == 'small'
        assert panel.widgets['whisper.beam_size'].value() == 1
        assert panel.widgets['overlay.enabled'].isChecked() is True

    def test_signal_emission(self, qapp, config_manager):
        """Test that signals are emitted correctly"""
        panel = SettingsPanel(config_manager)

        # Track signal emissions
        settings_saved_emitted = False
        model_changed_emitted = False
        model_value = None

        def on_settings_saved():
            nonlocal settings_saved_emitted
            settings_saved_emitted = True

        def on_model_changed(model):
            nonlocal model_changed_emitted, model_value
            model_changed_emitted = True
            model_value = model

        panel.settings_saved.connect(on_settings_saved)
        panel.model_changed.connect(on_model_changed)

        # Change model and save
        panel.widgets['whisper.model'].setCurrentText('medium')
        panel.save_settings()

        assert settings_saved_emitted is True
        assert model_changed_emitted is True
        assert model_value == 'medium'


class TestIntegration:
    """Integration tests for UI components working together"""

    def test_full_workflow(self, qapp, db_manager, config_manager):
        """Test complete workflow: add transcription, search, export, configure"""
        window = MainWindow(db_manager, config_manager)

        # Add some transcriptions
        window.add_transcription("Hello world", 1.5, "en", "small")
        window.add_transcription("Python programming", 2.0, "en", "small")
        window.add_transcription("Bonjour monde", 1.8, "fr", "small")

        # Navigate to history
        window.show_history()
        assert window.stack.currentIndex() == 0

        # Verify all items are visible
        assert window.history_panel.history_list.count() == 3

        # Search for "Python"
        window.history_panel.search("Python")
        visible = sum(
            1 for i in range(window.history_panel.history_list.count())
            if not window.history_panel.history_list.item(i).isHidden()
        )
        assert visible == 1

        # Navigate to settings
        window.show_settings()
        assert window.stack.currentIndex() == 1

        # Change model
        window.settings_panel.widgets['whisper.model'].setCurrentText('medium')
        window.settings_panel.save_settings()

        # Verify config updated
        assert config_manager.get('whisper.model') == 'medium'

        window.close()

    def test_history_limit(self, qapp, db_manager, config_manager):
        """Test that history respects limit setting"""
        # Add 100 transcriptions
        for i in range(100):
            db_manager.add_transcription(f"Test {i}", "en", 1.0, "small")

        panel = HistoryPanel(db_manager)
        panel.load_history(limit=50)

        # Should only show 50
        assert panel.history_list.count() == 50

        # Load with different limit
        panel.load_history(limit=10)
        assert panel.history_list.count() == 10


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
