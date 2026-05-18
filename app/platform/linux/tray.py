"""
Linux tray stub.

Linux UX keeps MainWindow as the primary entry point — no menu bar agent.
This module exposes the same `TrayController` interface as the macOS version
so call sites can construct it unconditionally if desired, but it is a no-op
on Linux.
"""
from __future__ import annotations

import logging
from PySide6.QtCore import QObject, Signal

logger = logging.getLogger(__name__)


class TrayController(QObject):
    """No-op TrayController on Linux. Signals are declared for API parity
    with the macOS version but never fire."""

    toggle_requested = Signal()
    open_window_requested = Signal()
    quit_requested = Signal()

    def __init__(self, icon_path=None, parent=None):
        super().__init__(parent)
        logger.debug("Linux TrayController: no-op")

    def show(self) -> None:
        pass

    def hide(self) -> None:
        pass

    def set_recording_state(self, is_recording: bool) -> None:
        pass

    def update_last_result(self, text: str) -> None:
        pass
