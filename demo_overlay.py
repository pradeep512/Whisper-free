#!/usr/bin/env python3
"""
Demo script for Dynamic Island Overlay

This script demonstrates the overlay in action with all modes.
Press Ctrl+C to exit.

Author: Whisper-Free Project
"""

import sys
import time
import random
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer

from app.ui.overlay import DynamicIslandOverlay, OverlayMode


def demo_overlay():
    """Demonstrate overlay functionality."""
    app = QApplication(sys.argv)
    overlay = DynamicIslandOverlay()

    print("Dynamic Island Overlay Demo")
    print("=" * 50)

    # Step 1: Show MINIMAL mode
    print("\n1. Showing MINIMAL mode (Ready state)")
    overlay.set_mode(OverlayMode.MINIMAL)
    overlay.show()
    QTimer.singleShot(2000, lambda: demo_listening(overlay))

    sys.exit(app.exec())


def demo_listening(overlay):
    """Demo LISTENING mode with animated waveform."""
    print("2. Showing LISTENING mode with waveform")
    overlay.set_mode(OverlayMode.LISTENING)

    # Simulate waveform data updates
    update_count = [0]

    def update_waveform():
        if update_count[0] < 60:  # 2 seconds at 30 FPS
            # Generate random waveform data
            levels = [random.uniform(0.2, 0.8) for _ in range(30)]
            overlay.update_waveform(levels)
            update_count[0] += 1
            QTimer.singleShot(33, update_waveform)  # ~30 FPS
        else:
            # Move to processing
            demo_processing(overlay)

    update_waveform()


def demo_processing(overlay):
    """Demo PROCESSING mode."""
    print("3. Showing PROCESSING mode")
    overlay.set_mode(OverlayMode.PROCESSING)
    QTimer.singleShot(2000, lambda: demo_result(overlay))


def demo_result(overlay):
    """Demo RESULT mode with auto-dismiss."""
    print("4. Showing RESULT mode (auto-dismisses after 2.5s)")
    overlay.set_result_text(
        "This is a sample transcription that demonstrates the result display"
    )
    QTimer.singleShot(3500, lambda: demo_copied(overlay))


def demo_copied(overlay):
    """Demo COPIED mode."""
    print("5. Showing COPIED mode (auto-dismisses after 1.5s)")
    overlay.show_copied_confirmation()
    QTimer.singleShot(2500, lambda: demo_hide(overlay))


def demo_hide(overlay):
    """Demo HIDDEN mode."""
    print("6. Hiding overlay (HIDDEN mode)")
    overlay.set_mode(OverlayMode.HIDDEN)
    QTimer.singleShot(1000, lambda: demo_complete(overlay))


def demo_complete(overlay):
    """Complete the demo."""
    print("\nDemo complete!")
    print("Overlay can be integrated with StateMachine for full functionality.")
    QTimer.singleShot(500, QApplication.quit)


if __name__ == "__main__":
    demo_overlay()
