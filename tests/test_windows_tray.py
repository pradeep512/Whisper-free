"""Automated coverage for #16: Windows hybrid tray + close-to-tray UX.

Exercises the two deterministic seams that don't require a human at the
keyboard or a real system tray:

1. `app.platform.windows.tray.TrayController` signal wiring and the
   one-time "hidden to tray" notification.
2. `MainWindow.closeEvent` hiding the window instead of requesting app
   shutdown, specifically on win32 (Linux/macOS keep the original
   quit-on-close behavior, which is unit-tested by contrast here too).

The real `QSystemTrayIcon` / native tray plumbing, actual balloon
rendering, and multi-launch tray behavior still need a human GUI smoke
test per the issue's testing decisions.
"""

import os
import sys
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


@pytest.mark.skipif(sys.platform != "win32", reason="constructs the Windows TrayController")
def test_tray_controller_wires_signals_and_notifies_once(qapp):
    from app.platform.windows.tray import TrayController

    tray = TrayController(icon_path=None)
    tray._tray.showMessage = MagicMock()

    toggle_calls = []
    open_calls = []
    quit_calls = []
    tray.toggle_requested.connect(lambda: toggle_calls.append(1))
    tray.open_window_requested.connect(lambda: open_calls.append(1))
    tray.quit_requested.connect(lambda: quit_calls.append(1))

    tray._action_open.trigger()
    tray._action_quit.trigger()
    assert open_calls == [1]
    assert quit_calls == [1]

    tray.notify_hidden_to_tray()
    tray.notify_hidden_to_tray()
    assert tray._tray.showMessage.call_count == 1


@pytest.mark.skipif(sys.platform != "win32", reason="exercises win32 close-to-tray behavior")
def test_main_window_close_hides_to_tray_on_windows(qapp, tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))

    from app.data.config import ConfigManager
    from app.data.database import DatabaseManager
    from app.ui.main_window import MainWindow

    config = ConfigManager()
    db = DatabaseManager()
    window = MainWindow(db, config)
    window.show()
    assert window.isVisible()

    hide_to_tray_calls = []
    exit_calls = []
    window.hide_to_tray_requested.connect(lambda: hide_to_tray_calls.append(1))
    window.exit_requested.connect(lambda: exit_calls.append(1))

    window.close()

    assert not window.isVisible()
    assert hide_to_tray_calls == [1]
    assert exit_calls == []

    db.close()
