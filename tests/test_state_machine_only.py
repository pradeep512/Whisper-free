#!/usr/bin/env python3
"""
Test StateMachine only (no GUI/X11 required)

This script tests the state machine component without requiring a display.
"""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.state_machine import StateMachine, ApplicationState
import threading
import time


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

    # Test get_state_name()
    assert state.get_state_name() == "idle"
    print("  ✓ get_state_name() works")

    # Test __repr__ and __str__
    repr_str = repr(state)
    str_str = str(state)
    assert "idle" in repr_str.lower()
    assert "idle" in str_str.lower()
    print("  ✓ __repr__ and __str__ work")

    print("  ✅ All StateMachine tests passed!\n")


def test_threading():
    """Test thread safety of state machine"""
    print("=== Testing Thread Safety ===")

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


def test_all_transitions():
    """Test all valid transitions systematically"""
    print("=== Testing All Valid Transitions ===")

    state = StateMachine()

    # From IDLE
    state.reset()
    assert state.transition_to(ApplicationState.RECORDING)
    print("  ✓ IDLE → RECORDING")

    state.reset()
    assert state.transition_to(ApplicationState.ERROR, error_message="Test")
    print("  ✓ IDLE → ERROR")

    # From RECORDING
    state.reset()
    state.transition_to(ApplicationState.RECORDING)
    assert state.transition_to(ApplicationState.PROCESSING)
    print("  ✓ RECORDING → PROCESSING")

    state.reset()
    state.transition_to(ApplicationState.RECORDING)
    assert state.transition_to(ApplicationState.IDLE)
    print("  ✓ RECORDING → IDLE")

    state.reset()
    state.transition_to(ApplicationState.RECORDING)
    assert state.transition_to(ApplicationState.ERROR, error_message="Test")
    print("  ✓ RECORDING → ERROR")

    # From PROCESSING
    state.reset()
    state.transition_to(ApplicationState.RECORDING)
    state.transition_to(ApplicationState.PROCESSING)
    assert state.transition_to(ApplicationState.COMPLETED)
    print("  ✓ PROCESSING → COMPLETED")

    state.reset()
    state.transition_to(ApplicationState.RECORDING)
    state.transition_to(ApplicationState.PROCESSING)
    assert state.transition_to(ApplicationState.ERROR, error_message="Test")
    print("  ✓ PROCESSING → ERROR")

    # From COMPLETED
    state.reset()
    state.transition_to(ApplicationState.RECORDING)
    state.transition_to(ApplicationState.PROCESSING)
    state.transition_to(ApplicationState.COMPLETED)
    assert state.transition_to(ApplicationState.IDLE)
    print("  ✓ COMPLETED → IDLE")

    state.reset()
    state.transition_to(ApplicationState.RECORDING)
    state.transition_to(ApplicationState.PROCESSING)
    state.transition_to(ApplicationState.COMPLETED)
    assert state.transition_to(ApplicationState.ERROR, error_message="Test")
    print("  ✓ COMPLETED → ERROR")

    # From ERROR
    state.reset()
    state.transition_to(ApplicationState.ERROR, error_message="Test")
    assert state.transition_to(ApplicationState.IDLE)
    print("  ✓ ERROR → IDLE")

    print("  ✅ All transition tests passed!\n")


def test_invalid_transitions():
    """Test that invalid transitions are rejected"""
    print("=== Testing Invalid Transitions ===")

    state = StateMachine()

    # From IDLE (invalid: PROCESSING, COMPLETED)
    state.reset()
    assert not state.transition_to(ApplicationState.PROCESSING)
    print("  ✓ IDLE → PROCESSING rejected")

    state.reset()
    assert not state.transition_to(ApplicationState.COMPLETED)
    print("  ✓ IDLE → COMPLETED rejected")

    # From RECORDING (invalid: RECORDING, COMPLETED)
    state.reset()
    state.transition_to(ApplicationState.RECORDING)
    assert not state.transition_to(ApplicationState.RECORDING)
    print("  ✓ RECORDING → RECORDING rejected")

    state.reset()
    state.transition_to(ApplicationState.RECORDING)
    assert not state.transition_to(ApplicationState.COMPLETED)
    print("  ✓ RECORDING → COMPLETED rejected")

    # From PROCESSING (invalid: IDLE, RECORDING, PROCESSING)
    state.reset()
    state.transition_to(ApplicationState.RECORDING)
    state.transition_to(ApplicationState.PROCESSING)
    assert not state.transition_to(ApplicationState.IDLE)
    print("  ✓ PROCESSING → IDLE rejected")

    state.reset()
    state.transition_to(ApplicationState.RECORDING)
    state.transition_to(ApplicationState.PROCESSING)
    assert not state.transition_to(ApplicationState.RECORDING)
    print("  ✓ PROCESSING → RECORDING rejected")

    state.reset()
    state.transition_to(ApplicationState.RECORDING)
    state.transition_to(ApplicationState.PROCESSING)
    assert not state.transition_to(ApplicationState.PROCESSING)
    print("  ✓ PROCESSING → PROCESSING rejected")

    # From COMPLETED (invalid: RECORDING, PROCESSING, COMPLETED)
    state.reset()
    state.transition_to(ApplicationState.RECORDING)
    state.transition_to(ApplicationState.PROCESSING)
    state.transition_to(ApplicationState.COMPLETED)
    assert not state.transition_to(ApplicationState.RECORDING)
    print("  ✓ COMPLETED → RECORDING rejected")

    state.reset()
    state.transition_to(ApplicationState.RECORDING)
    state.transition_to(ApplicationState.PROCESSING)
    state.transition_to(ApplicationState.COMPLETED)
    assert not state.transition_to(ApplicationState.PROCESSING)
    print("  ✓ COMPLETED → PROCESSING rejected")

    state.reset()
    state.transition_to(ApplicationState.RECORDING)
    state.transition_to(ApplicationState.PROCESSING)
    state.transition_to(ApplicationState.COMPLETED)
    assert not state.transition_to(ApplicationState.COMPLETED)
    print("  ✓ COMPLETED → COMPLETED rejected")

    # From ERROR (invalid: RECORDING, PROCESSING, COMPLETED, ERROR)
    state.reset()
    state.transition_to(ApplicationState.ERROR, error_message="Test")
    assert not state.transition_to(ApplicationState.RECORDING)
    print("  ✓ ERROR → RECORDING rejected")

    state.reset()
    state.transition_to(ApplicationState.ERROR, error_message="Test")
    assert not state.transition_to(ApplicationState.PROCESSING)
    print("  ✓ ERROR → PROCESSING rejected")

    state.reset()
    state.transition_to(ApplicationState.ERROR, error_message="Test")
    assert not state.transition_to(ApplicationState.COMPLETED)
    print("  ✓ ERROR → COMPLETED rejected")

    state.reset()
    state.transition_to(ApplicationState.ERROR, error_message="Test")
    assert not state.transition_to(ApplicationState.ERROR, error_message="Test2")
    print("  ✓ ERROR → ERROR rejected")

    print("  ✅ All invalid transition tests passed!\n")


if __name__ == "__main__":
    print("\n" + "=" * 50)
    print("Whisper-Free: State Machine Tests (No GUI)")
    print("=" * 50 + "\n")

    try:
        test_state_machine()
        test_all_transitions()
        test_invalid_transitions()
        test_threading()

        print("=" * 50)
        print("✅ All tests completed successfully!")
        print("=" * 50 + "\n")
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}\n")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}\n")
        import traceback
        traceback.print_exc()
        sys.exit(1)
