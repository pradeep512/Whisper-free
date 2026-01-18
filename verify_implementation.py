#!/usr/bin/env python3
"""
Quick verification that implementations work
"""
import sys
sys.path.insert(0, '.')

print("=" * 60)
print("VERIFYING IMPLEMENTATION")
print("=" * 60)

# Test 1: Import check
print("\n1. Testing imports...")
try:
    from app.core.state_machine import StateMachine, ApplicationState
    from app.core.hotkey_manager import HotkeyManager
    print("   ✓ Imports successful")
except Exception as e:
    print(f"   ✗ Import failed: {e}")
    sys.exit(1)

# Test 2: Create QApplication (needed for QObject)
print("\n2. Creating QApplication...")
try:
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QTimer
    app = QApplication(sys.argv)
    print("   ✓ QApplication created")
except Exception as e:
    print(f"   ✗ QApplication creation failed: {e}")
    sys.exit(1)

# Test 3: StateMachine creation
print("\n3. Testing StateMachine...")
try:
    state = StateMachine()
    print(f"   ✓ Created: {state}")
    print(f"   ✓ Current state: {state.current_state.value}")
    print(f"   ✓ Is busy: {state.is_busy()}")
except Exception as e:
    print(f"   ✗ StateMachine creation failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 4: State transitions
print("\n4. Testing state transitions...")
try:
    success_count = 0

    if state.transition_to(ApplicationState.RECORDING):
        print("   ✓ IDLE → RECORDING")
        success_count += 1

    if state.transition_to(ApplicationState.PROCESSING):
        print("   ✓ RECORDING → PROCESSING")
        success_count += 1

    if state.transition_to(ApplicationState.COMPLETED):
        print("   ✓ PROCESSING → COMPLETED")
        success_count += 1

    if state.transition_to(ApplicationState.IDLE):
        print("   ✓ COMPLETED → IDLE")
        success_count += 1

    # Test invalid transition
    if not state.transition_to(ApplicationState.PROCESSING):
        print("   ✓ Invalid transition correctly rejected")
        success_count += 1

    if success_count == 5:
        print(f"   ✓ All {success_count} transition tests passed")
    else:
        print(f"   ✗ Only {success_count}/5 tests passed")
        sys.exit(1)

except Exception as e:
    print(f"   ✗ State transition failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 5: Error state
print("\n5. Testing error state...")
try:
    state.reset()
    state.transition_to(ApplicationState.RECORDING)

    if state.transition_to(ApplicationState.ERROR, error_message="Test error"):
        print("   ✓ Error state with message")
    else:
        print("   ✗ Error state transition failed")
        sys.exit(1)

    # Try error without message (should raise ValueError)
    try:
        state.reset()
        state.transition_to(ApplicationState.ERROR)
        print("   ✗ Should have raised ValueError")
        sys.exit(1)
    except ValueError:
        print("   ✓ ValueError raised when error_message missing")

except Exception as e:
    print(f"   ✗ Error state test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 6: Reset and is_busy
print("\n6. Testing reset and is_busy...")
try:
    state.reset()
    if state.current_state == ApplicationState.IDLE:
        print("   ✓ Reset works")
    else:
        print("   ✗ Reset failed")
        sys.exit(1)

    if not state.is_busy():
        print("   ✓ is_busy() = False in IDLE")
    else:
        print("   ✗ is_busy() should be False")
        sys.exit(1)

    state.transition_to(ApplicationState.RECORDING)
    if state.is_busy():
        print("   ✓ is_busy() = True in RECORDING")
    else:
        print("   ✗ is_busy() should be True")
        sys.exit(1)

except Exception as e:
    print(f"   ✗ Reset/is_busy test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 7: HotkeyManager creation
print("\n7. Testing HotkeyManager...")
try:
    hotkey = HotkeyManager(hotkey="<ctrl>+<space>")
    print(f"   ✓ Created with hotkey: {hotkey.get_current_hotkey()}")
    print(f"   ✓ Is running: {hotkey.is_running()}")

    # Test invalid hotkey
    try:
        bad_hotkey = HotkeyManager(hotkey="")
        print("   ✗ Should have raised ValueError for empty hotkey")
        sys.exit(1)
    except ValueError:
        print("   ✓ ValueError raised for invalid hotkey")

except Exception as e:
    print(f"   ✗ HotkeyManager test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 8: Signals
print("\n8. Testing signal connections...")
try:
    state.reset()
    signal_count = [0]
    error_messages = []

    def on_state_change(new_state):
        signal_count[0] += 1

    def on_error(msg):
        error_messages.append(msg)

    state.state_changed.connect(on_state_change)
    state.error_occurred.connect(on_error)

    print("   ✓ Signals connected successfully")
    print("   Note: Signals will be tested in full application")

except Exception as e:
    print(f"   ✗ Signal connection failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 60)
print("✅ ALL VERIFICATION TESTS PASSED")
print("=" * 60)
print("\nImplementation is correct!")
print("\nNote: Interactive hotkey testing requires:")
print("  - X11 session (not Wayland)")
print("  - Manual keyboard input")
print("  - No conflicting hotkey bindings")
print("\nTo test hotkeys manually, run:")
print("  python tests/test_hotkey_state.py")
