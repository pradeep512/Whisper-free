"""
First-launch onboarding wizard for permissions (macOS-focused).

Shown on first launch (no config.yaml existed before this run) or when the
user clicks Settings → "Re-run setup…". Walks through Microphone access
(system prompt) and Accessibility access (deep-link to System Settings +
polling for grant).

On Linux the wizard is a no-op — current Linux behavior is preserved by
not invoking it from main.py at all.
"""
from __future__ import annotations

import logging
import sys

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QPushButton, QStackedWidget, QVBoxLayout,
    QWidget,
)

logger = logging.getLogger(__name__)


# Polling interval for Accessibility grant detection (ms).
_ACCESSIBILITY_POLL_MS = 500
# Step indices in the QStackedWidget.
_STEP_MIC = 0
_STEP_ACCESSIBILITY = 1
_STEP_DONE = 2


class OnboardingWizard(QDialog):
    """Two-step modal: Microphone → Accessibility → Done.

    Signals:
        finished_setup: Emitted when the user dismisses the wizard (any way).
    """

    finished_setup = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Welcome to Whisper-Free")
        self.setModal(True)
        self.setMinimumSize(560, 440)

        # Strip the help button (the "?" in the title bar on some platforms).
        flags = self.windowFlags() & ~Qt.WindowContextHelpButtonHint
        self.setWindowFlags(flags)

        self.stack = QStackedWidget(self)
        self.stack.addWidget(self._build_mic_step())          # index _STEP_MIC
        self.stack.addWidget(self._build_accessibility_step())  # _STEP_ACCESSIBILITY
        self.stack.addWidget(self._build_done_step())         # _STEP_DONE

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.addWidget(self.stack)

        # Poll Accessibility grant while on step 2.
        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(_ACCESSIBILITY_POLL_MS)
        self.poll_timer.timeout.connect(self._poll_accessibility)

        # Reflect existing permission state on open so re-run-setup is sensible.
        self._refresh_initial_state()

        logger.info("OnboardingWizard initialized")

    # ---------- step builders ----------

    def _build_mic_step(self) -> QWidget:
        w = QWidget(self)
        layout = QVBoxLayout(w)
        layout.setSpacing(12)

        title = QLabel("<h2>Microphone access</h2>")
        body = QLabel(
            "Whisper-Free needs to record audio from your microphone to "
            "transcribe your voice locally. Nothing leaves your computer."
        )
        body.setWordWrap(True)

        self.mic_status = QLabel("Not granted yet.")
        self.mic_status.setStyleSheet("color: #aaa; font-style: italic;")

        btn_row = QHBoxLayout()
        skip = QPushButton("Skip", w)
        skip.clicked.connect(lambda: self.stack.setCurrentIndex(_STEP_ACCESSIBILITY))
        grant = QPushButton("Request Access", w)
        grant.setDefault(True)
        grant.clicked.connect(self._request_microphone)
        btn_row.addStretch(1)
        btn_row.addWidget(skip)
        btn_row.addWidget(grant)

        layout.addWidget(title)
        layout.addWidget(body)
        layout.addStretch(1)
        layout.addWidget(self.mic_status)
        layout.addLayout(btn_row)
        return w

    def _build_accessibility_step(self) -> QWidget:
        w = QWidget(self)
        layout = QVBoxLayout(w)
        layout.setSpacing(12)

        title = QLabel("<h2>Accessibility access</h2>")
        body = QLabel(
            "Whisper-Free uses a global hotkey to start and stop recording "
            "from any application. macOS requires Accessibility access to "
            "watch for keys system-wide.\n\n"
            "<b>How to grant:</b>\n"
            "1. Click <b>Open Settings</b> below.\n"
            "2. Find 'Whisper-Free' in the list (use + to add it if missing).\n"
            "3. Toggle the switch on.\n"
            "4. Come back — this window detects the change automatically."
        )
        body.setWordWrap(True)
        body.setTextFormat(Qt.RichText)

        self.access_status = QLabel("Waiting for grant…")
        self.access_status.setStyleSheet("color: #aaa; font-style: italic;")

        btn_row = QHBoxLayout()
        skip = QPushButton("Skip", w)
        skip.clicked.connect(self._goto_done)
        open_btn = QPushButton("Open Settings", w)
        open_btn.setDefault(True)
        open_btn.clicked.connect(self._open_accessibility)
        btn_row.addStretch(1)
        btn_row.addWidget(skip)
        btn_row.addWidget(open_btn)

        layout.addWidget(title)
        layout.addWidget(body)
        layout.addStretch(1)
        layout.addWidget(self.access_status)
        layout.addLayout(btn_row)
        return w

    def _build_done_step(self) -> QWidget:
        w = QWidget(self)
        layout = QVBoxLayout(w)
        layout.setSpacing(12)

        title = QLabel("<h2>All set</h2>")
        body = QLabel(
            "Whisper-Free is ready. Press your hotkey to start recording. "
            "Look for the menu bar icon at the top of your screen."
        )
        body.setWordWrap(True)

        btn_row = QHBoxLayout()
        done = QPushButton("Get started", w)
        done.setDefault(True)
        done.clicked.connect(self._finish)
        btn_row.addStretch(1)
        btn_row.addWidget(done)

        layout.addWidget(title)
        layout.addWidget(body)
        layout.addStretch(1)
        layout.addLayout(btn_row)
        return w

    # ---------- step transitions / handlers ----------

    def _refresh_initial_state(self) -> None:
        """If permissions are already granted (re-run-setup), reflect it."""
        try:
            from app.platform import hotkey_perms
            if hotkey_perms.is_microphone_granted():
                self.mic_status.setText("Granted ✓")
            if hotkey_perms.is_accessibility_granted():
                self.access_status.setText("Granted ✓")
        except Exception as e:
            logger.debug(f"_refresh_initial_state: {e}")

    def _request_microphone(self) -> None:
        try:
            from app.platform import hotkey_perms
            hotkey_perms.request_microphone_access(self._on_mic_result)
        except Exception as e:
            logger.error(f"Microphone request failed: {e}")
            self.mic_status.setText(f"Request failed: {e}")

    def _on_mic_result(self, granted: bool) -> None:
        # Marshal to the main thread via the dialog's event loop.
        QTimer.singleShot(0, lambda: self._handle_mic_result(granted))

    def _handle_mic_result(self, granted: bool) -> None:
        if granted:
            self.mic_status.setText("Granted ✓")
            # Auto-advance to next step after a short beat.
            QTimer.singleShot(400, lambda: self.stack.setCurrentIndex(_STEP_ACCESSIBILITY))
        else:
            self.mic_status.setText(
                "Denied. Open System Settings → Privacy → Microphone to grant."
            )

    def _open_accessibility(self) -> None:
        try:
            from app.platform import hotkey_perms
            hotkey_perms.open_accessibility_settings()
        except Exception as e:
            logger.error(f"Could not open Accessibility settings: {e}")
        # Start polling regardless of whether the open succeeded — the
        # user may have opened it manually.
        self.poll_timer.start()

    def _poll_accessibility(self) -> None:
        try:
            from app.platform import hotkey_perms
            if hotkey_perms.is_accessibility_granted():
                self.poll_timer.stop()
                self.access_status.setText("Granted ✓")
                QTimer.singleShot(400, self._goto_done)
        except Exception as e:
            logger.debug(f"_poll_accessibility: {e}")

    def _goto_done(self) -> None:
        self.poll_timer.stop()
        self.stack.setCurrentIndex(_STEP_DONE)

    def _finish(self) -> None:
        self.poll_timer.stop()
        self.finished_setup.emit()
        self.accept()

    # ---------- Qt overrides ----------

    def closeEvent(self, event) -> None:
        # Treat closing the window like skipping to the end.
        self.poll_timer.stop()
        self.finished_setup.emit()
        super().closeEvent(event)


def should_show_on_launch() -> bool:
    """Return True if the onboarding wizard should appear on this platform."""
    return sys.platform == 'darwin'
