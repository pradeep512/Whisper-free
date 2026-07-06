"""
Windows "Open at Login" support via the per-user Run registry key.

Writes/removes a value under
HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run — the standard
per-user autostart mechanism that needs no admin rights and no service
installation. Windows launches the referenced command for the signing-in
user automatically.
"""
from __future__ import annotations

import logging
import sys

logger = logging.getLogger(__name__)

_RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
_RUN_VALUE_NAME = "Whisper-Free"


def _launch_command() -> str:
    """Build the command Windows should run on sign-in.

    Frozen (PyInstaller) builds re-invoke the installed .exe directly;
    running from source re-invokes the current interpreter with
    `-m app.main` so dev checkouts also work.
    """
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    return f'"{sys.executable}" -m app.main'


def set_open_at_login(enabled: bool) -> bool:
    """Toggle the HKCU Run value. Returns True on success."""
    try:
        import winreg
    except ImportError:
        logger.warning("winreg unavailable; cannot toggle Open at Login.")
        return False

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _RUN_KEY_PATH, 0, winreg.KEY_SET_VALUE
        ) as key:
            if enabled:
                winreg.SetValueEx(
                    key, _RUN_VALUE_NAME, 0, winreg.REG_SZ, _launch_command()
                )
            else:
                try:
                    winreg.DeleteValue(key, _RUN_VALUE_NAME)
                except FileNotFoundError:
                    pass
        return True
    except OSError as e:
        logger.error(
            f"Open at Login {'enable' if enabled else 'disable'} failed: {e}"
        )
        return False


def is_open_at_login_enabled() -> bool:
    """Query whether the HKCU Run value is currently set."""
    try:
        import winreg
    except ImportError:
        return False

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _RUN_KEY_PATH, 0, winreg.KEY_READ
        ) as key:
            winreg.QueryValueEx(key, _RUN_VALUE_NAME)
            return True
    except OSError:
        return False
