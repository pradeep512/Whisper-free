"""Tests for app.platform.windows.autolaunch (HKCU Run key).

Windows-only; uses a test-specific registry value name (monkeypatched) so
runs never touch the real "Whisper-Free" Run entry, and cleans up after
itself regardless of test outcome.
"""
import sys

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != 'win32', reason="Windows registry autostart is win32-only"
)


@pytest.fixture(autouse=True)
def isolated_value_name(monkeypatch):
    from app.platform.windows import autolaunch

    monkeypatch.setattr(autolaunch, "_RUN_VALUE_NAME", "Whisper-Free-Test")
    yield
    autolaunch.set_open_at_login(False)


def test_enable_creates_run_value():
    from app.platform.windows import autolaunch

    assert autolaunch.set_open_at_login(True) is True
    assert autolaunch.is_open_at_login_enabled() is True


def test_disable_removes_run_value():
    from app.platform.windows import autolaunch

    autolaunch.set_open_at_login(True)
    assert autolaunch.set_open_at_login(False) is True
    assert autolaunch.is_open_at_login_enabled() is False


def test_disable_when_not_set_is_a_no_op_success():
    from app.platform.windows import autolaunch

    assert autolaunch.is_open_at_login_enabled() is False
    assert autolaunch.set_open_at_login(False) is True
    assert autolaunch.is_open_at_login_enabled() is False


def test_launch_command_uses_module_invocation_from_source():
    from app.platform.windows import autolaunch

    cmd = autolaunch._launch_command()
    assert cmd.startswith('"')
    assert "-m app.main" in cmd


def test_launch_command_uses_bare_exe_when_frozen(monkeypatch):
    from app.platform.windows import autolaunch

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    cmd = autolaunch._launch_command()
    assert "-m app.main" not in cmd
