"""
Windows system tray icon for Whisper-Free.

Unlike the macOS menu bar (which is the primary entry point while the main
window stays hidden), Windows runs a hybrid model: the main window shows on
launch and closing it hides to the tray rather than quitting, so the global
hotkey keeps working in the background. Left-click toggles recording;
right-click shows a context menu (Open Window / Quit).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QAction, QColor, QCursor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

logger = logging.getLogger(__name__)

# Size for the synthesized fallback tray icon.
_FALLBACK_ICON_SIZE = 32


class TrayController(QObject):
    """System tray icon for Windows.

    Signals:
        toggle_requested:      Emitted on left-click (start/stop recording).
        open_window_requested: Emitted on context "Open Window".
        quit_requested:        Emitted on context "Quit Whisper-Free".
    """

    toggle_requested = Signal()
    open_window_requested = Signal()
    quit_requested = Signal()

    def __init__(self, icon_path: Optional[Path] = None, parent: Optional[QObject] = None):
        super().__init__(parent)

        icon = self._build_icon(icon_path)

        self._tray = QSystemTrayIcon(icon, self)
        self._tray.setToolTip("Whisper-Free")

        self._menu = QMenu()

        self._action_open = QAction("Open Window", self._menu)
        self._action_open.triggered.connect(self.open_window_requested.emit)
        self._menu.addAction(self._action_open)

        self._menu.addSeparator()

        self._action_quit = QAction("Quit Whisper-Free", self._menu)
        self._action_quit.triggered.connect(self.quit_requested.emit)
        self._menu.addAction(self._action_quit)

        self._tray.setContextMenu(self._menu)
        self._tray.activated.connect(self._on_activated)

        self._shown_hide_notice = False

        logger.info("TrayController initialized (Windows system tray)")

    # ---- public API ----

    def show(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            logger.warning("System tray not available; tray icon cannot be shown")
            return
        self._tray.show()
        logger.info("System tray icon shown")

    def hide(self) -> None:
        self._tray.hide()

    def set_recording_state(self, is_recording: bool) -> None:
        """Reflect recording state in the tooltip."""
        self._tray.setToolTip("Whisper-Free — Recording" if is_recording else "Whisper-Free")

    def update_last_result(self, text: str) -> None:
        """Reserved for future enhancement (show last transcript via balloon)."""
        # No-op for v1.

    def notify_hidden_to_tray(self) -> None:
        """Show a one-time balloon explaining the window went to the tray.

        Only fires the first time this is called per process run — repeated
        close-to-tray actions in the same session don't re-notify.
        """
        if self._shown_hide_notice:
            return
        self._shown_hide_notice = True
        self._tray.showMessage(
            "Whisper-Free is still running",
            "Whisper-Free keeps running in the tray so the hotkey stays "
            "active. Right-click the tray icon to reopen or quit.",
            QSystemTrayIcon.MessageIcon.Information,
            5000,
        )

    # ---- internals ----

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        """Left-click toggles recording; the context menu is handled by Qt
        automatically via setContextMenu() on right-click."""
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.toggle_requested.emit()

    def _build_icon(self, icon_path: Optional[Path]) -> QIcon:
        """Load the tray icon, falling back to a Qt-drawn placeholder."""
        if icon_path is not None and icon_path.exists():
            logger.debug(f"Loaded tray icon from {icon_path}")
            return QIcon(str(icon_path))

        logger.info(
            "No tray icon asset found; using Qt-drawn placeholder. "
            "Provide assets/tray-icon.ico for proper rendering."
        )
        return self._draw_fallback_icon()

    @staticmethod
    def _draw_fallback_icon() -> QIcon:
        """Draw a simple microphone glyph on a transparent background."""
        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QBrush

        sz = _FALLBACK_ICON_SIZE
        pixmap = QPixmap(sz, sz)
        pixmap.fill(Qt.transparent)

        painter = QPainter(pixmap)
        try:
            painter.setRenderHint(QPainter.Antialiasing)
            white = QColor(255, 255, 255, 255)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QBrush(white))

            cap_w = sz * 0.30
            cap_h = sz * 0.45
            cap_x = (sz - cap_w) / 2.0
            cap_y = sz * 0.16
            painter.drawRoundedRect(
                QRectF(cap_x, cap_y, cap_w, cap_h),
                cap_w / 2.0, cap_w / 2.0,
            )

            stroke = max(2, int(sz * 0.055))
            pen = QPen(white, stroke)
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            bracket_w = sz * 0.46
            bracket_h = sz * 0.18
            bracket_x = (sz - bracket_w) / 2.0
            bracket_y = sz * 0.55
            painter.drawArc(
                QRectF(bracket_x, bracket_y, bracket_w, bracket_h * 2),
                0 * 16, -180 * 16,
            )

            stand_top_y = bracket_y + bracket_h
            stand_bot_y = sz * 0.86
            mid_x = sz / 2.0
            painter.drawLine(
                int(mid_x), int(stand_top_y),
                int(mid_x), int(stand_bot_y),
            )

            base_half = sz * 0.13
            painter.drawLine(
                int(mid_x - base_half), int(stand_bot_y),
                int(mid_x + base_half), int(stand_bot_y),
            )
        finally:
            painter.end()

        return QIcon(pixmap)
