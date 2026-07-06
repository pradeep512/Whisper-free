"""Hotkey normalization tests, incl. Windows-relevant combos (Ctrl+Space,
function keys) needed for the Windows port's default hotkey and Settings
reconfiguration (issue #14 acceptance criteria).
"""
import pytest

from app.core.hotkey_manager import HotkeyManager


@pytest.fixture
def manager():
    return HotkeyManager(hotkey="<ctrl>+<space>")


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("ctrl+space", "<ctrl>+<space>"),
        ("ctrl+shift+v", "<ctrl>+<shift>+v"),
        ("alt+r", "<alt>+r"),
        ("ctrl+f1", "<ctrl>+<f1>"),
        ("alt+f12", "<alt>+<f12>"),
        ("<ctrl>+<space>", "<ctrl>+<space>"),
        ("CTRL+SPACE", "<ctrl>+<space>"),
    ],
)
def test_normalize_hotkey(manager, raw, expected):
    assert manager._normalize_hotkey(raw) == expected
