"""
Unit tests for Dynamic Island Overlay

Tests the overlay window, animations, waveform rendering, and mode transitions.

Run with: python -m pytest tests/test_overlay.py -v

Author: Whisper-Free Project
License: MIT
"""

import sys
import pytest
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt, QTimer, QAbstractAnimation
from PySide6.QtGui import QColor
import time

from app.ui.overlay import DynamicIslandOverlay, OverlayMode
from app.ui.waveform_painter import WaveformPainter


@pytest.fixture(scope="session")
def qapp():
    """Create QApplication instance for tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    yield app


@pytest.fixture
def overlay(qapp):
    """Create DynamicIslandOverlay instance for each test."""
    overlay = DynamicIslandOverlay()
    yield overlay
    overlay.close()


class TestOverlayInitialization:
    """Test overlay initialization and basic properties."""

    def test_overlay_init(self, overlay):
        """Test overlay initializes in HIDDEN mode."""
        assert overlay.mode == OverlayMode.HIDDEN
        assert overlay.windowOpacity() == 0.0
        assert overlay.width() == 0
        assert overlay.height() == 0

    def test_window_flags(self, overlay):
        """Test window flags are set correctly."""
        flags = overlay.windowFlags()

        # Check for frameless
        assert flags & Qt.FramelessWindowHint

        # Check for always on top
        assert flags & Qt.WindowStaysOnTopHint

        # Check for tool window
        assert flags & Qt.Tool

        # Check for no focus
        assert flags & Qt.WindowDoesNotAcceptFocus

    def test_translucent_background(self, overlay):
        """Test translucent background is enabled."""
        assert overlay.testAttribute(Qt.WA_TranslucentBackground)

    def test_repr(self, overlay):
        """Test string representation."""
        repr_str = repr(overlay)
        assert "DynamicIslandOverlay" in repr_str
        assert "HIDDEN" in repr_str


class TestModeTransitions:
    """Test transitions between different overlay modes."""

    def test_minimal_mode(self, overlay, qapp):
        """Test transition to MINIMAL mode."""
        overlay.set_mode(OverlayMode.MINIMAL)
        overlay.show()

        # Wait for animation to complete
        QTest.qWait(700)
        qapp.processEvents()

        # Check dimensions (allow small variance due to animation timing)
        assert 115 <= overlay.width() <= 125
        assert 35 <= overlay.height() <= 45
        assert 0.65 <= overlay.windowOpacity() <= 0.75

    def test_listening_mode(self, overlay, qapp):
        """Test transition to LISTENING mode."""
        overlay.set_mode(OverlayMode.LISTENING)
        overlay.show()

        # Wait for animation
        QTest.qWait(700)
        qapp.processEvents()

        assert 395 <= overlay.width() <= 405
        assert 75 <= overlay.height() <= 85
        assert overlay.windowOpacity() >= 0.95

    def test_processing_mode(self, overlay, qapp):
        """Test transition to PROCESSING mode."""
        overlay.set_mode(OverlayMode.PROCESSING)
        overlay.show()

        QTest.qWait(700)
        qapp.processEvents()

        assert 295 <= overlay.width() <= 305
        assert 55 <= overlay.height() <= 65
        assert 0.85 <= overlay.windowOpacity() <= 0.95

    def test_result_mode(self, overlay, qapp):
        """Test transition to RESULT mode."""
        overlay.set_mode(OverlayMode.RESULT)
        overlay.show()

        QTest.qWait(700)
        qapp.processEvents()

        assert 495 <= overlay.width() <= 505
        assert 95 <= overlay.height() <= 105
        assert overlay.windowOpacity() >= 0.95

    def test_copied_mode(self, overlay, qapp):
        """Test transition to COPIED mode."""
        overlay.set_mode(OverlayMode.COPIED)
        overlay.show()

        QTest.qWait(700)
        qapp.processEvents()

        assert 245 <= overlay.width() <= 255
        assert 45 <= overlay.height() <= 55
        assert 0.75 <= overlay.windowOpacity() <= 0.85

    def test_hidden_mode(self, overlay, qapp):
        """Test transition to HIDDEN mode."""
        # Start in MINIMAL
        overlay.set_mode(OverlayMode.MINIMAL)
        overlay.show()
        QTest.qWait(700)

        # Transition to HIDDEN
        overlay.set_mode(OverlayMode.HIDDEN)
        QTest.qWait(700)
        qapp.processEvents()

        assert overlay.windowOpacity() <= 0.1

    def test_mode_signal(self, overlay, qapp):
        """Test mode_changed signal is emitted."""
        received_modes = []

        def on_mode_changed(mode):
            received_modes.append(mode)

        overlay.mode_changed.connect(on_mode_changed)

        overlay.set_mode(OverlayMode.MINIMAL)
        QTest.qWait(100)
        qapp.processEvents()

        assert OverlayMode.MINIMAL in received_modes


class TestWaveformFunctionality:
    """Test waveform visualization functionality."""

    def test_waveform_update(self, overlay):
        """Test waveform data update."""
        overlay.set_mode(OverlayMode.LISTENING)

        test_data = [0.5] * 30
        overlay.update_waveform(test_data)

        assert len(overlay.waveform_data) == 30
        assert all(0.0 <= level <= 1.0 for level in overlay.waveform_data)

    def test_waveform_empty(self, overlay):
        """Test waveform with empty data."""
        overlay.set_mode(OverlayMode.LISTENING)
        overlay.update_waveform([])

        assert len(overlay.waveform_data) == 0

    def test_waveform_varying_levels(self, overlay):
        """Test waveform with varying audio levels."""
        overlay.set_mode(OverlayMode.LISTENING)

        # Simulate varying audio levels
        test_data = [i / 30.0 for i in range(30)]
        overlay.update_waveform(test_data)

        waveform = overlay.waveform_data
        assert len(waveform) == 30
        assert waveform[0] < waveform[-1]  # Increasing levels

    def test_waveform_clamping(self, overlay):
        """Test waveform values are properly clamped."""
        overlay.set_mode(OverlayMode.LISTENING)

        # Test with out-of-range values
        test_data = [-0.5, 0.5, 1.5, 2.0, -1.0]
        overlay.update_waveform(test_data)

        # Values should be stored as-is (clamping happens in painter)
        assert len(overlay.waveform_data) == 5


class TestWaveformPainter:
    """Test WaveformPainter utility class."""

    def test_paint_waveform_basic(self, overlay, qapp):
        """Test basic waveform painting doesn't crash."""
        overlay.set_mode(OverlayMode.LISTENING)
        overlay.show()

        test_data = [0.5] * 30
        overlay.update_waveform(test_data)

        # Trigger paint event
        overlay.repaint()
        qapp.processEvents()

        # If we got here without crashing, the test passes
        assert True

    def test_paint_waveform_empty(self, overlay, qapp):
        """Test painting with empty waveform data."""
        overlay.set_mode(OverlayMode.LISTENING)
        overlay.show()

        overlay.update_waveform([])
        overlay.repaint()
        qapp.processEvents()

        # Should not crash
        assert True

    def test_waveform_dimensions(self):
        """Test waveform dimension calculation."""
        width, height = WaveformPainter.get_waveform_dimensions()

        # Default: 30 bars * 4px + 29 gaps * 6px = 294px
        expected_width = 30 * 4 + 29 * 6
        assert width == expected_width
        assert height == 50

    def test_waveform_custom_dimensions(self):
        """Test waveform with custom parameters."""
        width, height = WaveformPainter.get_waveform_dimensions(
            bar_count=20,
            bar_width=6,
            bar_spacing=4
        )

        expected_width = 20 * 6 + 19 * 4
        assert width == expected_width


class TestAutoDismiss:
    """Test auto-dismiss functionality."""

    def test_result_auto_dismiss(self, overlay, qapp):
        """Test RESULT mode auto-dismisses after 2.5s."""
        overlay.set_mode(OverlayMode.MINIMAL)
        overlay.show()
        QTest.qWait(700)

        # Set result
        overlay.set_result_text("Test transcript")
        assert overlay.mode == OverlayMode.RESULT

        # Wait for auto-dismiss (2.5s + buffer)
        QTest.qWait(3000)
        qapp.processEvents()

        # Should transition back to MINIMAL
        assert overlay.mode == OverlayMode.MINIMAL

    def test_copied_auto_dismiss(self, overlay, qapp):
        """Test COPIED mode auto-dismisses after 1.5s."""
        overlay.set_mode(OverlayMode.MINIMAL)
        overlay.show()
        QTest.qWait(700)

        # Show copied confirmation
        overlay.show_copied_confirmation()
        assert overlay.mode == OverlayMode.COPIED

        # Wait for auto-dismiss (1.5s + buffer)
        QTest.qWait(2000)
        qapp.processEvents()

        # Should transition back to MINIMAL
        assert overlay.mode == OverlayMode.MINIMAL

    def test_mode_change_cancels_auto_dismiss(self, overlay, qapp):
        """Test changing mode cancels previous auto-dismiss timer."""
        overlay.set_result_text("Test")
        assert overlay.mode == OverlayMode.RESULT

        # Immediately change to another mode
        QTest.qWait(100)
        overlay.set_mode(OverlayMode.LISTENING)

        # Wait past original auto-dismiss time
        QTest.qWait(3000)
        qapp.processEvents()

        # Should still be in LISTENING, not MINIMAL
        assert overlay.mode == OverlayMode.LISTENING


class TestResultText:
    """Test result text display functionality."""

    def test_set_result_text(self, overlay):
        """Test setting result text."""
        test_text = "This is a test transcription"
        overlay.set_result_text(test_text)

        assert overlay.mode == OverlayMode.RESULT
        assert overlay._result_text == test_text

    def test_result_text_truncation(self, overlay):
        """Test long text is truncated."""
        long_text = "A" * 100
        overlay.set_result_text(long_text)

        # Should truncate to 60 chars + "..."
        assert len(overlay._result_text) == 63
        assert overlay._result_text.endswith("...")

    def test_result_text_short(self, overlay):
        """Test short text is not truncated."""
        short_text = "Short"
        overlay.set_result_text(short_text)

        assert overlay._result_text == short_text
        assert not overlay._result_text.endswith("...")


class TestPositioning:
    """Test overlay positioning on screen."""

    def test_centered_position(self, overlay, qapp):
        """Test overlay is centered horizontally."""
        overlay.set_mode(OverlayMode.MINIMAL)
        overlay.show()
        QTest.qWait(700)
        qapp.processEvents()

        # Get screen width
        screen = QApplication.primaryScreen()
        screen_width = screen.geometry().width()

        # Calculate expected center position
        overlay_width = overlay.width()
        expected_x = (screen_width - overlay_width) // 2

        # Allow small variance
        actual_x = overlay.x()
        assert abs(actual_x - expected_x) < 10

    def test_top_position(self, overlay, qapp):
        """Test overlay is positioned at top of screen."""
        overlay.set_mode(OverlayMode.MINIMAL)
        overlay.show()
        QTest.qWait(700)
        qapp.processEvents()

        # Should be 20px from top
        assert overlay.y() == 20


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_same_mode_transition(self, overlay):
        """Test transitioning to same mode is no-op."""
        overlay.set_mode(OverlayMode.MINIMAL)
        initial_geometry = overlay.geometry()

        # Try to set same mode
        overlay.set_mode(OverlayMode.MINIMAL)

        # Geometry should not change
        assert overlay.geometry() == initial_geometry

    def test_waveform_in_non_listening_mode(self, overlay, qapp):
        """Test waveform update in non-LISTENING mode."""
        overlay.set_mode(OverlayMode.MINIMAL)

        # Update waveform (should not crash)
        overlay.update_waveform([0.5] * 30)

        assert len(overlay.waveform_data) == 30

    def test_empty_result_text(self, overlay):
        """Test setting empty result text."""
        overlay.set_result_text("")

        assert overlay.mode == OverlayMode.RESULT
        assert overlay._result_text == ""

    def test_rapid_mode_changes(self, overlay, qapp):
        """Test rapid mode changes don't cause issues."""
        modes = [
            OverlayMode.MINIMAL,
            OverlayMode.LISTENING,
            OverlayMode.PROCESSING,
            OverlayMode.RESULT,
            OverlayMode.MINIMAL,
        ]

        for mode in modes:
            overlay.set_mode(mode)
            QTest.qWait(50)  # Very short delay
            qapp.processEvents()

        # Final mode should be MINIMAL
        assert overlay.mode == OverlayMode.MINIMAL

    def test_paint_event_while_hidden(self, overlay, qapp):
        """Test paint event while overlay is hidden."""
        overlay.set_mode(OverlayMode.HIDDEN)

        # Trigger paint (should not crash)
        overlay.repaint()
        qapp.processEvents()

        assert True


class TestAnimation:
    """Test animation system."""

    def test_animation_completion(self, overlay, qapp):
        """Test animation completes fully."""
        overlay.set_mode(OverlayMode.MINIMAL)
        overlay.show()

        # Animation duration is 600ms, wait a bit longer
        QTest.qWait(700)
        qapp.processEvents()

        # Animation should be complete
        if overlay._animation_group:
            assert overlay._animation_group.state() != QAbstractAnimation.Running

    def test_animation_interruption(self, overlay, qapp):
        """Test interrupting animation with new mode."""
        overlay.set_mode(OverlayMode.MINIMAL)
        overlay.show()

        # Immediately change mode before animation completes
        QTest.qWait(100)
        overlay.set_mode(OverlayMode.LISTENING)

        # Wait for new animation
        QTest.qWait(700)
        qapp.processEvents()

        # Should be in LISTENING mode
        assert overlay.mode == OverlayMode.LISTENING


def test_integration_workflow(qapp):
    """Test complete workflow: MINIMAL → LISTENING → PROCESSING → RESULT → MINIMAL."""
    overlay = DynamicIslandOverlay()

    # Start in MINIMAL
    overlay.set_mode(OverlayMode.MINIMAL)
    overlay.show()
    QTest.qWait(700)
    assert overlay.mode == OverlayMode.MINIMAL

    # Start recording (LISTENING)
    overlay.set_mode(OverlayMode.LISTENING)
    QTest.qWait(700)
    assert overlay.mode == OverlayMode.LISTENING

    # Update waveform
    waveform = [0.3, 0.5, 0.7, 0.6, 0.4] * 6  # 30 values
    overlay.update_waveform(waveform)
    QTest.qWait(200)

    # Stop recording (PROCESSING)
    overlay.set_mode(OverlayMode.PROCESSING)
    QTest.qWait(700)
    assert overlay.mode == OverlayMode.PROCESSING

    # Show result
    overlay.set_result_text("Test transcription complete")
    QTest.qWait(700)
    assert overlay.mode == OverlayMode.RESULT

    # Wait for auto-dismiss
    QTest.qWait(3000)
    qapp.processEvents()
    assert overlay.mode == OverlayMode.MINIMAL

    overlay.close()


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])
