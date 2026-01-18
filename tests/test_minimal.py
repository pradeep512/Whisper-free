#!/usr/bin/env python3
"""
Minimal test with QApplication
"""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from app.core.state_machine import StateMachine, ApplicationState
from app.core.hotkey_manager import HotkeyManager

def run_tests():
    print("\n=== Testing StateMachine ===")

    state = StateMachine()
    print(f"✓ Created: {state}")

    # Test transitions
    assert state.transition_to(ApplicationState.RECORDING)
    print("✓ IDLE → RECORDING")

    assert state.transition_to(ApplicationState.PROCESSING)
    print("✓ RECORDING → PROCESSING")

    assert state.transition_to(ApplicationState.COMPLETED)
    print("✓ PROCESSING → COMPLETED")

    assert state.transition_to(ApplicationState.IDLE)
    print("✓ COMPLETED → IDLE")

    # Test invalid transition
    assert not state.transition_to(ApplicationState.PROCESSING)
    print("✓ Invalid transition rejected")

    # Test error state
    state.transition_to(ApplicationState.RECORDING)
    assert state.transition_to(ApplicationState.ERROR, error_message="Test error")
    print("✓ Error state")

    # Test reset
    state.reset()
    assert state.current_state == ApplicationState.IDLE
    print("✓ Reset")

    # Test is_busy
    assert not state.is_busy()
    state.transition_to(ApplicationState.RECORDING)
    assert state.is_busy()
    print("✓ is_busy()")

    print("\n=== Testing HotkeyManager ===")

    hotkey = HotkeyManager(hotkey="<ctrl>+<space>")
    print(f"✓ Created with hotkey: {hotkey.get_current_hotkey()}")
    print(f"✓ Is running: {hotkey.is_running()}")

    print("\n✅ All tests passed!")
    QApplication.quit()

if __name__ == "__main__":
    app = QApplication(sys.argv)

    # Run tests after event loop starts
    QTimer.singleShot(100, run_tests)

    sys.exit(app.exec())
