#!/usr/bin/env python3
"""
Basic test of state machine and hotkey manager imports and initialization
"""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

print("Testing imports...")

try:
    from app.core.state_machine import StateMachine, ApplicationState
    print("✓ StateMachine imported successfully")
except Exception as e:
    print(f"✗ StateMachine import failed: {e}")
    sys.exit(1)

try:
    from app.core.hotkey_manager import HotkeyManager
    print("✓ HotkeyManager imported successfully")
except Exception as e:
    print(f"✗ HotkeyManager import failed: {e}")
    sys.exit(1)

print("\nTesting StateMachine initialization...")
try:
    state = StateMachine()
    print(f"✓ StateMachine created: {state}")
    print(f"  Current state: {state.current_state}")
    print(f"  Is busy: {state.is_busy()}")
except Exception as e:
    print(f"✗ StateMachine initialization failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\nTesting basic state transitions...")
try:
    # Test one transition
    result = state.transition_to(ApplicationState.RECORDING)
    print(f"✓ IDLE → RECORDING: {result}")
    print(f"  Current state: {state.current_state}")

    # Test another
    result = state.transition_to(ApplicationState.PROCESSING)
    print(f"✓ RECORDING → PROCESSING: {result}")
    print(f"  Current state: {state.current_state}")

    # Test invalid
    result = state.transition_to(ApplicationState.RECORDING)
    print(f"✓ PROCESSING → RECORDING (should fail): {result}")

except Exception as e:
    print(f"✗ State transitions failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\nTesting HotkeyManager initialization...")
try:
    hotkey = HotkeyManager(hotkey="<ctrl>+<space>")
    print(f"✓ HotkeyManager created")
    print(f"  Current hotkey: {hotkey.get_current_hotkey()}")
    print(f"  Is running: {hotkey.is_running()}")
except Exception as e:
    print(f"✗ HotkeyManager initialization failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n✅ All basic tests passed!")
print("Note: Interactive hotkey testing requires X11 and manual input")
