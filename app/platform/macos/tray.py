"""
macOS menu bar tray icon for Whisper-Free.

On macOS, QSystemTrayIcon maps to NSStatusItem in the system menu bar.
Left-click toggles recording (primary action). Right-click / Control-click
shows the context menu (Toggle / Open Window / Quit).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, QPoint, Qt, Signal
from PySide6.QtGui import (
    QAction, QColor, QCursor, QFont, QIcon, QPainter, QPen, QPixmap,
)
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

logger = logging.getLogger(__name__)


# Size for the synthesized fallback menu-bar icon (rendered at @2x).
_FALLBACK_ICON_SIZE = 36


class TrayController(QObject):
    """Menu bar icon for macOS.

    Signals:
        toggle_requested:      Emitted on left-click (or context "Toggle Recording").
        open_window_requested: Emitted on context "Open Window…".
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

        # Context menu (right-click). Keep references so Qt doesn't GC them.
        self._menu = QMenu()
        self._action_toggle = QAction("Toggle Recording", self._menu)
        self._action_toggle.triggered.connect(self.toggle_requested.emit)
        self._menu.addAction(self._action_toggle)

        self._menu.addSeparator()

        self._action_open = QAction("Open Window…", self._menu)
        self._action_open.triggered.connect(self.open_window_requested.emit)
        self._menu.addAction(self._action_open)

        self._menu.addSeparator()

        self._action_quit = QAction("Quit Whisper-Free", self._menu)
        self._action_quit.triggered.connect(self.quit_requested.emit)
        self._menu.addAction(self._action_quit)

        # IMPORTANT: do NOT setContextMenu on macOS. With a context menu
        # set, NSStatusItem hijacks left-clicks to open the menu, which
        # defeats the click-to-toggle UX. Instead, we keep the QMenu
        # around and pop it up manually on right-click (Context reason).
        self._tray.activated.connect(self._on_activated)

        logger.info("TrayController initialized (macOS menu bar)")

    # ---- public API ----

    def show(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            logger.warning(
                "System tray not available; menu bar icon cannot be shown"
            )
            return
        self._tray.show()
        logger.info("Menu bar icon shown")

    def hide(self) -> None:
        self._tray.hide()

    def set_recording_state(self, is_recording: bool) -> None:
        """Reflect recording state in the icon and menu label.

        For now, just updates the menu label and tooltip. A future enhancement
        can swap to a "recording" icon variant.
        """
        if is_recording:
            self._action_toggle.setText("Stop Recording")
            self._tray.setToolTip("Whisper-Free — Recording")
        else:
            self._action_toggle.setText("Toggle Recording")
            self._tray.setToolTip("Whisper-Free")

    def update_last_result(self, text: str) -> None:
        """Reserved for future enhancement (show last transcript in the menu)."""
        # No-op for v1; a future popover widget will surface this.

    # ---- internals ----

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        """Route clicks per the standard Mac dictation app pattern.

        Left-click  → toggle recording (start/stop)
        Right-click → open the context menu (Toggle / Open Window / Quit)
        Double-click → same as left-click (treat as toggle)
        """
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.toggle_requested.emit()
        elif reason == QSystemTrayIcon.Context:
            # Pop the menu under the cursor. macOS positions it sensibly
            # because the cursor is right at the status item when clicked.
            self._menu.popup(QCursor.pos())

    def _build_icon(self, icon_path: Optional[Path]) -> QIcon:
        """Load the menu-bar icon, falling back to a Qt-drawn placeholder.

        Mac menu bar icons should be **template images** (monochrome with
        alpha, system-tinted). If a proper template asset exists at
        `icon_path`, use it. Otherwise, draw a simple "W" placeholder so the
        app still has a recognizable menu bar slot during development.
        Phase 9 polish: replace the placeholder with a designed mic glyph
        and ship `assets/menu-bar-icon.png` (16x16 @1x, 32x32 @2x).
        """
        if icon_path is not None and icon_path.exists():
            icon = QIcon(str(icon_path))
            # If the asset is authored as a template (monochrome+alpha), set
            # isMask so macOS tints it correctly in light/dark mode.
            icon.setIsMask(True)
            logger.debug(f"Loaded menu bar icon from {icon_path}")
            return icon

        logger.info(
            "No menu-bar icon asset found; using Qt-drawn placeholder. "
            "Provide assets/menu-bar-icon.png for proper rendering."
        )
        return self._draw_fallback_icon()

    @staticmethod
    def _draw_fallback_icon() -> QIcon:
        """Draw a simple microphone glyph on a transparent background.

        Authored as a template image (white-with-alpha) so macOS tints it
        for light/dark menu bar when setIsMask(True).

        Geometry, scaled to a 36-px pixmap:
          - mic body: rounded rectangle, ~10w x 14h, centered-top
          - stand:    vertical line under the body
          - base:     short horizontal line at the bottom
        """
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

            # Mic capsule — rounded rect, 30% wide, 45% tall, top-centered.
            cap_w = sz * 0.30
            cap_h = sz * 0.45
            cap_x = (sz - cap_w) / 2.0
            cap_y = sz * 0.16
            painter.drawRoundedRect(
                QRectF(cap_x, cap_y, cap_w, cap_h),
                cap_w / 2.0, cap_w / 2.0,
            )

            # U-shaped pickup (the stand bracket below the mic).
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
                0 * 16, -180 * 16,  # bottom half of an ellipse
            )

            # Stand: vertical line from the bracket bottom to the base.
            stand_top_y = bracket_y + bracket_h
            stand_bot_y = sz * 0.86
            mid_x = sz / 2.0
            painter.drawLine(
                int(mid_x), int(stand_top_y),
                int(mid_x), int(stand_bot_y),
            )

            # Base: short horizontal line at the bottom.
            base_half = sz * 0.13
            painter.drawLine(
                int(mid_x - base_half), int(stand_bot_y),
                int(mid_x + base_half), int(stand_bot_y),
            )
        finally:
            painter.end()

        icon = QIcon(pixmap)
        icon.setIsMask(True)
        return icon
