"""
Custom widgets that render exactly per our theme (no platform-native
overrides leaking through Qt's style system).
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor, QFontMetrics, QPainter, QPen,
)
from PySide6.QtWidgets import QCheckBox


class ModernCheckBox(QCheckBox):
    """A Mac-style checkbox with full custom paint.

    Why a subclass rather than just QSS: QCheckBox::indicator with
    border + background + image works fine on Linux, but on macOS Qt
    delegates to the native NSButton style which ignores most of our
    rules and renders the system accent-blue check. Custom paint
    guarantees the same look on all platforms.

    Layout:
        [indicator] [text]

    Indicator: 18 px rounded square. Filled with accent when checked.
    White checkmark stroke inside when checked.
    """

    INDICATOR_SIZE = 18
    INDICATOR_RADIUS = 5
    INDICATOR_TO_TEXT = 10
    ROW_PADDING_V = 6

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setMouseTracking(True)
        self._hover = False

    # ---- Qt event hooks ----

    def enterEvent(self, event):  # noqa: D401
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def sizeHint(self):
        fm = QFontMetrics(self.font())
        text_w = fm.horizontalAdvance(self.text())
        text_h = fm.height()
        w = self.INDICATOR_SIZE + self.INDICATOR_TO_TEXT + text_w + 4
        h = max(self.INDICATOR_SIZE, text_h) + self.ROW_PADDING_V * 2
        from PySide6.QtCore import QSize
        return QSize(w, h)

    def paintEvent(self, event):
        # Pulled inside paintEvent so the theme is read at draw-time —
        # if accent ever changes live, the next repaint picks it up.
        from app.ui.theme import (
            BG, BG_HOVER, SEPARATOR, TEXT, TEXT_MUTED, system_accent,
        )

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        size = self.INDICATOR_SIZE
        x = 1
        y = (self.height() - size) // 2
        indicator = QRectF(x, y, size, size)

        checked = self.isChecked()
        enabled = self.isEnabled()

        # --- indicator ---
        if checked:
            fill = QColor(system_accent() if enabled else BG_HOVER)
            painter.setBrush(fill)
            painter.setPen(QPen(fill, 1))
        else:
            painter.setBrush(QColor(BG))
            border_color = system_accent() if (self._hover and enabled) else SEPARATOR
            painter.setPen(QPen(QColor(border_color), 1.5))
        painter.drawRoundedRect(indicator, self.INDICATOR_RADIUS, self.INDICATOR_RADIUS)

        # --- checkmark ---
        if checked:
            check_pen = QPen(QColor("white") if enabled else QColor(TEXT_MUTED), 2.0,
                             Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
            painter.setPen(check_pen)
            cx = x + size / 2.0
            cy = y + size / 2.0
            # Three-point check: down-left → down-mid → up-right
            painter.drawLine(QPointF(cx - 4.5, cy + 0.5),
                             QPointF(cx - 1.0, cy + 4.0))
            painter.drawLine(QPointF(cx - 1.0, cy + 4.0),
                             QPointF(cx + 5.0, cy - 3.5))

        # --- label ---
        text_x = x + size + self.INDICATOR_TO_TEXT
        text_rect = QRectF(text_x, 0, self.width() - text_x, self.height())
        painter.setPen(QColor(TEXT if enabled else TEXT_MUTED))
        painter.setFont(self.font())
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, self.text())

        painter.end()
