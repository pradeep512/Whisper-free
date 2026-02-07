"""
IPC Server for Whisper-Free (Wayland hotkey support)

Provides a QLocalServer-based IPC mechanism so external commands can
control the running application. This enables Wayland hotkey support:
the user configures a system shortcut (e.g., Ctrl+Space) to run
`whisper --toggle`, which sends a command to this server.

Protocol:
    Client connects to server named "whisper-free", sends a UTF-8
    command string, and disconnects. No response is sent.

Commands:
    "toggle" - Toggle recording (start if idle, stop if recording)
"""

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket
import logging

logger = logging.getLogger(__name__)


class IPCServer(QObject):
    """
    Local IPC server using QLocalServer (Unix domain socket).

    Signals:
        command_received(str): Emitted when a valid command is received
    """

    command_received = Signal(str)

    SERVER_NAME = "whisper-free"

    def __init__(self):
        super().__init__()
        self._server = QLocalServer(self)
        self._server.newConnection.connect(self._on_new_connection)

    def start(self) -> bool:
        """
        Start listening for IPC connections.

        Returns:
            True if server started, False on failure
        """
        # Remove stale socket from previous crash
        QLocalServer.removeServer(self.SERVER_NAME)

        if not self._server.listen(self.SERVER_NAME):
            logger.error(f"IPC server failed to start: {self._server.errorString()}")
            return False

        logger.info(f"IPC server listening on '{self.SERVER_NAME}'")
        return True

    def stop(self):
        """Stop the IPC server."""
        if self._server.isListening():
            self._server.close()
            logger.info("IPC server stopped")

    def _on_new_connection(self):
        """Handle incoming IPC connection."""
        while self._server.hasPendingConnections():
            socket = self._server.nextPendingConnection()
            if socket is None:
                continue

            # Wait briefly for data (non-blocking with timeout)
            if socket.waitForReadyRead(500):
                data = socket.readAll().data().decode('utf-8').strip()
                logger.info(f"IPC command received: '{data}'")
                if data:
                    self.command_received.emit(data)

            socket.disconnectFromServer()


def send_ipc_command(command: str) -> bool:
    """
    Send a command to the running Whisper-Free instance.

    Args:
        command: Command string (e.g., "toggle")

    Returns:
        True if command was sent, False if app is not running
    """
    socket = QLocalSocket()
    socket.connectToServer(IPCServer.SERVER_NAME)

    if not socket.waitForConnected(1000):
        return False

    socket.write(command.encode('utf-8'))
    socket.flush()
    socket.waitForBytesWritten(1000)
    socket.disconnectFromServer()
    return True
