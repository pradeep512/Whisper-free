"""
Windows permission helpers — stubs.

Windows doesn't gate global low-level keyboard hooks or microphone capture
behind a runtime grant the way macOS does (pynput's Win32 hook and
sounddevice/PortAudio just work once the process starts). All checks return
True so call-site logic — and the onboarding wizard, which is skipped
entirely on Windows — can run unconditionally.
"""
from __future__ import annotations

from typing import Callable


def is_accessibility_granted() -> bool:
    """Always True on Windows — no equivalent permission model."""
    return True


def open_accessibility_settings() -> None:
    """No-op on Windows."""
    return


def is_microphone_granted() -> bool:
    """Always True on Windows — no runtime microphone grant to query."""
    return True


def request_microphone_access(callback: Callable[[bool], None]) -> None:
    """No-op on Windows; immediately calls the callback with True."""
    callback(True)
