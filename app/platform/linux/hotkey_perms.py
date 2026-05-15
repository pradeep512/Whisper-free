"""
Linux permission helpers — stubs.

Linux X11 doesn't gate global hotkeys behind a permission system, and
microphone access is governed by file permissions on /dev/snd/* (no
runtime prompt). All checks return True so call-site logic can run
unconditionally.
"""
from __future__ import annotations

from typing import Callable


def is_accessibility_granted() -> bool:
    """Always True on Linux — no equivalent permission model."""
    return True


def open_accessibility_settings() -> None:
    """No-op on Linux."""
    return


def is_microphone_granted() -> bool:
    """Always True on Linux — handled by group membership / udev."""
    return True


def request_microphone_access(callback: Callable[[bool], None]) -> None:
    """No-op on Linux; immediately calls the callback with True."""
    callback(True)
