#!/usr/bin/env python3
"""
Test HotkeyManager and StateMachine

This script tests the core components of the Whisper-Free hotkey system
and state management.
"""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QThread, QTimer
from app.core.hotkey_manager import HotkeyManager
from app.core.state_machine import StateMachine, ApplicationState


def test_state_machine():
    """Test state machine transitions"""
    print("=== Testing StateMachine ===")

    state = StateMachine()

    # Valid transitions
    assert state.transition_to(ApplicationState.RECORDING), "IDLE → RECORDING failed"
    assert state.current_state == ApplicationState.RECORDING
    print("  ✓ IDLE → RECORDING")

    assert state.transition_to(ApplicationState.PROCESSING), "RECORDING → PROCESSING failed"
    assert state.current_state == ApplicationState.PROCESSING
    print("  ✓ RECORDING → PROCESSING")

    assert state.transition_to(ApplicationState.COMPLETED), "PROCESSING → COMPLETED failed"
    assert state.current_state == ApplicationState.COMPLETED
    print("  ✓ PROCESSING → COMPLETED")

    assert state.transition_to(ApplicationState.IDLE), "COMPLETED → IDLE failed"
    assert state.current_state == ApplicationState.IDLE
    print("  ✓ COMPLETED → IDLE")

    # Invalid transition
    assert not state.transition_to(ApplicationState.PROCESSING), "Should reject IDLE → PROCESSING"
    print("  ✓ Invalid transition rejected")

    # Error state
    assert state.transition_to(ApplicationState.RECORDING)
    assert state.transition_to(ApplicationState.ERROR, error_message="Test error")
    assert state.current_state == ApplicationState.ERROR
    print("  ✓ Error state transition")

    # Recovery
    state.reset()
    assert state.current_state == ApplicationState.IDLE
    print("  ✓ Reset to IDLE")

    # is_busy()
    assert not state.is_busy()
    state.transition_to(ApplicationState.RECORDING)
    assert state.is_busy()
    print("  ✓ is_busy() works")

    # Test can_transition_to()
    state.reset()
    assert state.can_transition_to(ApplicationState.RECORDING)
    assert not state.can_transition_to(ApplicationState.PROCESSING)
    assert state.can_transition_to(ApplicationState.ERROR)  # Always allowed
    print("  ✓ can_transition_to() works")

    # Test error state without message (should raise ValueError)
    try:
        state.reset()
        state.transition_to(ApplicationState.ERROR)
        assert False, "Should raise ValueError"
    except ValueError:
        print("  ✓ Error state requires message")

    # Test cancel recording (RECORDING → IDLE)
    state.reset()
    state.transition_to(ApplicationState.RECORDING)
    assert state.transition_to(ApplicationState.IDLE), "RECORDING → IDLE failed"
    assert state.current_state == ApplicationState.IDLE
    print("  ✓ RECORDING → IDLE (cancel)")

    # Test full workflow
    state.reset()
    assert state.transition_to(ApplicationState.RECORDING)
    assert state.transition_to(ApplicationState.PROCESSING)
    assert state.transition_to(ApplicationState.COMPLETED)
    assert state.transition_to(ApplicationState.IDLE)
    print("  ✓ Full workflow: IDLE → RECORDING → PROCESSING → COMPLETED → IDLE")

    print("  ✅ All StateMachine tests passed!\n")


def test_hotkey_manager():
    """Test hotkey manager (interactive)"""
    print("=== Testing HotkeyManager ===")
    print("  This test requires manual interaction.")
    print("  Press CTRL+Space 3 times, then CTRL+C to exit")
    print()

    app = QApplication(sys.argv)

    hotkey = HotkeyManager(hotkey="<ctrl>+<space>")
    press_count = [0]  # Use list for closure

    def on_hotkey():
        press_count[0] += 1
        print(f"  ✓ Hotkey detected! (#{press_count[0]})")
        if press_count[0] >= 3:
            print("  ✅ HotkeyManager test passed!")
            QTimer.singleShot(1000, app.quit)

    hotkey.hotkey_pressed.connect(on_hotkey)

    # Run in thread
    thread = QThread()
    hotkey.moveToThread(thread)
    thread.started.connect(hotkey.start)
    thread.start()

    try:
        sys.exit(app.exec())
    except KeyboardInterrupt:
        print("\n  Test interrupted")
        hotkey.stop()
        thread.quit()
        thread.wait()


def test_hotkey_validation():
    """Test hotkey format validation"""
    print("=== Testing Hotkey Validation ===")

    # Valid hotkeys
    try:
        hk1 = HotkeyManager(hotkey="<ctrl>+<space>")
        print("  ✓ Valid: <ctrl>+<space>")
    except ValueError:
        assert False, "Should accept <ctrl>+<space>"

    try:
        hk2 = HotkeyManager(hotkey="<ctrl>+<shift>+v")
        print("  ✓ Valid: <ctrl>+<shift>+v")
    except ValueError:
        assert False, "Should accept <ctrl>+<shift>+v"

    try:
        hk3 = HotkeyManager(hotkey="<alt>+r")
        print("  ✓ Valid: <alt>+r")
    except ValueError:
        assert False, "Should accept <alt>+r"

    # Invalid hotkeys
    try:
        hk_invalid = HotkeyManager(hotkey="")
        assert False, "Should reject empty hotkey"
    except ValueError:
        print("  ✓ Rejected: empty string")

    # Test is_running()
    hk = HotkeyManager(hotkey="<ctrl>+<space>")
    assert not hk.is_running()
    print("  ✓ is_running() returns False initially")

    # Test get_current_hotkey()
    assert hk.get_current_hotkey() == "<ctrl>+<space>"
    print("  ✓ get_current_hotkey() works")

    print("  ✅ All validation tests passed!\n")


def test_state_machine_signals():
    """Test state machine signal emission"""
    print("=== Testing StateMachine Signals ===")

    app = QApplication(sys.argv)
    state = StateMachine()

    state_changes = []
    errors = []

    def on_state_change(new_state):
        state_changes.append(new_state)

    def on_error(error_msg):
        errors.append(error_msg)

    state.state_changed.connect(on_state_change)
    state.error_occurred.connect(on_error)

    # Test normal transitions
    state.transition_to(ApplicationState.RECORDING)
    assert len(state_changes) == 1
    assert state_changes[0] == ApplicationState.RECORDING
    print("  ✓ state_changed signal emitted")

    # Test error signal
    state.transition_to(ApplicationState.ERROR, error_message="Test error")
    assert len(errors) == 1
    assert errors[0] == "Test error"
    assert len(state_changes) == 2
    print("  ✓ error_occurred signal emitted")

    # Test reset signal
    state.reset()
    assert len(state_changes) == 3
    assert state_changes[2] == ApplicationState.IDLE
    print("  ✓ reset() emits signal")

    print("  ✅ All signal tests passed!\n")


def test_threading():
    """Test thread safety of state machine"""
    print("=== Testing Thread Safety ===")

    import threading
    import time

    state = StateMachine()
    errors = []

    def worker():
        try:
            for _ in range(100):
                # Rapid state transitions
                if state.current_state == ApplicationState.IDLE:
                    state.transition_to(ApplicationState.RECORDING)
                elif state.current_state == ApplicationState.RECORDING:
                    state.transition_to(ApplicationState.PROCESSING)
                elif state.current_state == ApplicationState.PROCESSING:
                    state.transition_to(ApplicationState.COMPLETED)
                elif state.current_state == ApplicationState.COMPLETED:
                    state.transition_to(ApplicationState.IDLE)
                time.sleep(0.001)
        except Exception as e:
            errors.append(e)

    # Create multiple threads
    threads = [threading.Thread(target=worker) for _ in range(5)]

    # Start all threads
    for t in threads:
        t.start()

    # Wait for completion
    for t in threads:
        t.join()

    # Check for errors
    if errors:
        print(f"  ✗ Thread safety test failed: {errors}")
        assert False
    else:
        print("  ✓ No race conditions detected")

    print("  ✅ Thread safety test passed!\n")


if __name__ == "__main__":
    print("\n" + "=" * 50)
    print("Whisper-Free: Hotkey & State Machine Tests")
    print("=" * 50 + "\n")

    # Non-interactive tests
    test_state_machine()
    test_hotkey_validation()
    test_state_machine_signals()
    test_threading()

    # Interactive test
    print("Run interactive hotkey test? (y/n): ", end='')
    try:
        response = input().lower()
        if response == 'y':
            test_hotkey_manager()
        else:
            print("  Skipped interactive test")
    except (EOFError, KeyboardInterrupt):
        print("\n  Skipped interactive test")

    print("\n" + "=" * 50)
    print("✅ All tests completed!")
    print("=" * 50 + "\n")
