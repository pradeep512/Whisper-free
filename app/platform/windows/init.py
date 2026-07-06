"""
Windows-specific app initialization hooks.

Called once from `app.platform.platform_init(app)` during
`WhisperFreeApp.__init__`, after components exist but before the event
loop starts.

Responsibilities:
- Construct and wire the system tray TrayController.
- Wire MainWindow's hide-to-tray close behavior to a one-time balloon.
- Make the bundled ffmpeg.exe (packaging/windows/#20) discoverable so
  MP3/M4A/WebM file transcription works with no system FFmpeg on PATH.
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def init_windows(app) -> None:
    """Apply Windows-specific runtime initialization.

    Called from platform_init(app) at the end of WhisperFreeApp.__init__,
    after all core/UI components exist.

    Args:
        app: The WhisperFreeApp instance.
    """
    ensure_bundled_ffmpeg_on_path()
    _install_tray_icon(app)


def ensure_bundled_ffmpeg_on_path() -> bool:
    """Prepend the frozen bundle's directory to PATH if it ships ffmpeg.exe.

    audioread (used by librosa for MP3/M4A/WebM) shells out to whatever
    `ffmpeg` resolves to via the OS's normal PATH search -- it never takes an
    explicit binary path. The PyInstaller onedir bundle (packaging/windows/
    Whisper-Free.spec) places ffmpeg.exe next to Whisper-Free.exe, so
    prepending that directory makes it discoverable with no user setup.

    No-op when not running frozen, or when the bundle has no ffmpeg.exe
    (e.g. a dev/source run, or a CPU-only build missing the asset) -- the
    existing system-FFmpeg-on-PATH behavior is unaffected either way.

    Returns:
        True if the bundled ffmpeg.exe was found and PATH was updated.
    """
    if not getattr(sys, 'frozen', False):
        return False

    bundle_dir = Path(sys.executable).resolve().parent
    ffmpeg_exe = bundle_dir / 'ffmpeg.exe'
    if not ffmpeg_exe.exists():
        return False

    bundle_dir_str = str(bundle_dir)
    path = os.environ.get('PATH', '')
    if bundle_dir_str not in path.split(os.pathsep):
        os.environ['PATH'] = bundle_dir_str + os.pathsep + path
    logger.info(f"Bundled ffmpeg.exe found at {ffmpeg_exe}; prepended to PATH")
    return True


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
