"""
Windows-specific app initialization hooks.

Called once from `app.platform.platform_init(app)` during
`WhisperFreeApp.__init__`, after components exist but before the event
loop starts.

Responsibilities:
- Construct and wire the system tray TrayController.
- Wire MainWindow's hide-to-tray close behavior to a one-time balloon.
"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def init_windows(app) -> None:
    """Apply Windows-specific runtime initialization.

    Called from platform_init(app) at the end of WhisperFreeApp.__init__,
    after all core/UI components exist.

    Args:
        app: The WhisperFreeApp instance.
    """
    _install_tray_icon(app)


def _install_tray_icon(app) -> None:
    """Construct the system tray TrayController and wire its signals."""
    from app.platform.windows.tray import TrayController

    icon_path = _find_tray_icon()

    tray = TrayController(icon_path=icon_path, parent=app)

    tray.toggle_requested.connect(app.on_hotkey_pressed)
    tray.open_window_requested.connect(_show_main_window_factory(app))
    tray.quit_requested.connect(app.request_exit)

    # Closing the main window hides it to the tray instead of quitting
    # (MainWindow.closeEvent emits this only on win32); show the one-time
    # "still running" balloon so the user knows where it went.
    app.main_window.hide_to_tray_requested.connect(tray.notify_hidden_to_tray)

    tray.show()

    # Keep the tray controller alive on the app for the lifetime of the process.
    app.tray = tray
    logger.info("System tray installed and wired")


def _show_main_window_factory(app):
    """Return a slot that shows + raises + activates the main window."""
    def _show():
        try:
            app.main_window.show()
            app.main_window.raise_()
            app.main_window.activateWindow()
        except Exception as e:
            logger.error(f"Failed to show main window: {e}")
    return _show


def _find_tray_icon() -> Path | None:
    """Locate the tray icon asset, if any.

    Looks for `assets/tray-icon.ico` first (the designed asset). Falls back
    to None — TrayController will then draw a placeholder.
    """
    here = Path(__file__).resolve()
    # app/platform/windows/init.py -> repo root is parents[3]
    repo_root = here.parents[3]
    candidates = [
        repo_root / 'assets' / 'tray-icon.ico',
        repo_root / 'assets' / 'tray-icon.png',
    ]
    for c in candidates:
        if c.exists():
            return c
    return None
