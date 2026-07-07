"""Automated coverage for #17: Windows single-instance surface-existing-exit-new.

Exercises the deterministic seams that don't require an interactive session
or a real second OS process:

1. `app.core.ipc_server` round-trip: a client can detect whether a server is
   listening (`send_ipc_command`) and the server delivers a "focus" command
   payload to its `command_received` signal.
2. `WhisperFreeApp._on_ipc_command`/`_focus_main_window` routing: a "focus"
   IPC command restores a minimized window and raises/activates it.
3. `app.main._try_focus_running_instance()` reports whether a running
   instance answered, reusing any QCoreApplication already alive in-process
   (so it's safe to call under pytest, where other test modules may already
   hold the process-wide QApplication singleton).

The actual second-process launch, duplicate tray icon avoidance, and window
restore-from-minimized-and-foreground behavior on a real desktop still need
a human smoke test on Windows per the issue's testing decisions.
"""

import os
import sys
import time
import uuid
from unittest.mock import MagicMock

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QCoreApplication.instance()
    if app is None:
        app = QCoreApplication(sys.argv)
    return app


def _unique_server_name():
    """A fresh IPC pipe name per test invocation.

    A fixed name is unsafe on Windows: if a prior test process was killed
    while its IPCServer was listening (e.g. a timed-out CI run), the named
    pipe leaks and IPCServer.start()'s removeServer() cannot clear a pipe
    owned by a now-dead process. A later run reusing that name then connects
    to the dead pipe and silently drops the payload. A uuid per run makes
    every server-backed test immune to any leaked pipe from a previous run.
    """
    return f"whisper-free-test-{uuid.uuid4().hex}"


def _pump_until(qapp, predicate, timeout_s=2.0):
    """Process Qt events until `predicate()` is true or `timeout_s` elapses.

    QLocalServer's newConnection delivery on Windows named pipes needs the
    OS to actually dispatch the pipe-ready event between processEvents()
    calls; a tight busy loop without yielding can starve that dispatch.
    """
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        qapp.processEvents()
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


def test_send_ipc_command_false_when_nothing_listening(qapp):
    from app.core.ipc_server import send_ipc_command

    assert send_ipc_command("whisper-free-test-nobody-listening") is False


def test_ipc_server_delivers_focus_payload(qapp, monkeypatch):
    """The server delivers a client's payload verbatim to command_received.

    Exercises the real production client path (send_ipc_command), not a
    hand-rolled raw QLocalSocket: on Windows named pipes an eagerly
    disconnected/garbage-collected client socket tears the pipe down before
    the single-threaded in-process server reads it, which makes a raw-socket
    round-trip racy. send_ipc_command's fixed lifetime handling (socket
    parented to the QCoreApplication, no early disconnectFromServer) is what
    the app actually uses, so that is what we assert against here.
    """
    from app.core.ipc_server import IPCServer, send_ipc_command

    monkeypatch.setattr(IPCServer, "SERVER_NAME", _unique_server_name())

    server = IPCServer()
    received = []
    server.command_received.connect(received.append)
    assert server.start()

    try:
        assert send_ipc_command("focus") is True
        assert _pump_until(qapp, lambda: received)
        assert received == ["focus"]
    finally:
        server.stop()


def test_on_ipc_command_focus_calls_focus_main_window():
    from app.main import WhisperFreeApp

    fake_self = MagicMock()
    WhisperFreeApp._on_ipc_command(fake_self, "focus")
    fake_self._focus_main_window.assert_called_once()


def test_focus_main_window_restores_from_minimized():
    from app.main import WhisperFreeApp

    fake_self = MagicMock()
    fake_self.main_window.isMinimized.return_value = True
    WhisperFreeApp._focus_main_window(fake_self)
    fake_self.main_window.showNormal.assert_called_once()
    fake_self.main_window.show.assert_not_called()
    fake_self.main_window.raise_.assert_called_once()
    fake_self.main_window.activateWindow.assert_called_once()


def test_focus_main_window_shows_when_not_minimized():
    from app.main import WhisperFreeApp

    fake_self = MagicMock()
    fake_self.main_window.isMinimized.return_value = False
    WhisperFreeApp._focus_main_window(fake_self)
    fake_self.main_window.show.assert_called_once()
    fake_self.main_window.showNormal.assert_not_called()
    fake_self.main_window.raise_.assert_called_once()
    fake_self.main_window.activateWindow.assert_called_once()


def test_try_focus_running_instance_false_when_nothing_running(qapp):
    from app.main import _try_focus_running_instance

    assert _try_focus_running_instance() is False


def test_try_focus_running_instance_true_and_delivers_focus(qapp, monkeypatch):
    from app.core.ipc_server import IPCServer
    from app.main import _try_focus_running_instance

    monkeypatch.setattr(IPCServer, "SERVER_NAME", _unique_server_name())

    server = IPCServer()
    received = []
    server.command_received.connect(received.append)
    assert server.start()

    try:
        assert _try_focus_running_instance() is True

        assert _pump_until(qapp, lambda: received)
        assert received == ["focus"]
    finally:
        server.stop()
