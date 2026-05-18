"""
Cross-platform theme helpers.

Centralizes font stack, accent color, padding, and QSS fragments so all
panels render consistently. On macOS the system accent color (from
System Settings → Appearance → Accent color) is honored automatically;
on Linux a tasteful default blue is used.
"""
from __future__ import annotations

import sys

from PySide6.QtGui import QColor

# ---------------------------------------------------------------------------
# Palette helpers
# ---------------------------------------------------------------------------

# Constant dark palette. Designed against macOS dark-mode wallpapers but works
# fine on Linux too. We pick our own neutrals rather than QPalette so the look
# is stable across desktop environments.
BG          = "#1c1c1e"   # window background        (apple "systemGray6 dark")
BG_ELEVATED = "#2a2a2c"   # cards / popovers
BG_HOVER    = "#3a3a3c"
BG_PRESSED  = "#48484a"
SEPARATOR   = "#3a3a3c"
TEXT        = "#f2f2f7"
TEXT_MUTED  = "#8e8e93"
TEXT_DIM    = "#636366"
DANGER      = "#ff3b30"
SUCCESS     = "#34c759"
WARNING     = "#ff9f0a"

# macOS spacing rhythm (8 / 12 / 16 / 24).
PAD_XS = 4
PAD_S  = 8
PAD_M  = 12
PAD_L  = 16

# Corner radii — macOS Sonoma+ uses generous rounding.
RADIUS_S  = 6
RADIUS_M  = 8
RADIUS_L  = 12


def system_accent() -> str:
    """Return the app accent color.

    Set to macOS systemOrange (dark mode variant). To honor the user's
    chosen macOS accent color (System Settings → Appearance → Accent),
    bridge via pyobjc and read NSColor.controlAccentColor directly —
    a Tier 2 enhancement.
    """
    return "#ff9f0a"   # macOS systemOrange (dark mode)


def selection_bg() -> str:
    """Translucent accent for selected sidebar items, etc.

    Mac convention: selected nav items get a subtle accent tint, not a
    solid-color fill. Bright accent fills are reserved for actual buttons.
    """
    # Translucent systemOrange — same hue as system_accent(), ~24% alpha.
    return "rgba(255, 159, 10, 60)"


def accent_hover() -> str:
    """Slightly lighter accent for hover states."""
    return _shift(system_accent(), 1.12)


def accent_pressed() -> str:
    """Slightly darker accent for pressed states."""
    return _shift(system_accent(), 0.88)


def font_stack() -> str:
    """CSS font-family stack appropriate for the OS."""
    if sys.platform == 'darwin':
        return '-apple-system, "SF Pro Text", "Helvetica Neue", sans-serif'
    if sys.platform.startswith('linux'):
        return 'Inter, "Ubuntu", "DejaVu Sans", sans-serif'
    return '"Segoe UI", sans-serif'


def _shift(hex_color: str, factor: float) -> str:
    """Multiply the lightness of a color by `factor` (1.0 = unchanged)."""
    c = QColor(hex_color)
    h, s, l, a = c.getHslF()
    l = max(0.0, min(1.0, l * factor))
    c.setHslF(h, s, l, a)
    return c.name()


# ---------------------------------------------------------------------------
# QSS fragments — composed by panels into their setStyleSheet calls.
# ---------------------------------------------------------------------------

def main_window_qss() -> str:
    """Top-level theme applied by MainWindow."""
    return f"""
        QMainWindow {{ background-color: {BG}; }}

        QWidget {{
            background-color: {BG};
            color: {TEXT};
            font-family: {font_stack()};
            font-size: 13px;
        }}

        QLabel {{ background: transparent; }}

        QToolTip {{
            background-color: {BG_ELEVATED};
            color: {TEXT};
            border: 1px solid {SEPARATOR};
            border-radius: {RADIUS_S}px;
            padding: 4px 8px;
        }}

        /* Sidebar — Mac-style translucent pill on selection */
        QListWidget {{
            background-color: {BG};
            border: none;
            border-right: 1px solid {SEPARATOR};
            outline: none;
            padding: 8px 6px;
        }}
        QListWidget::item {{
            padding: 7px 12px;
            margin: 1px 6px;
            background-color: transparent;
            border-radius: {RADIUS_M}px;
            color: {TEXT_MUTED};
        }}
        QListWidget::item:selected {{
            background-color: {selection_bg()};
            color: {TEXT};
            font-weight: 600;
        }}
        QListWidget::item:hover:!selected {{
            background-color: {BG_HOVER};
            color: {TEXT};
        }}

        /* Status bar — quieter than the default */
        QStatusBar {{
            background-color: {BG_ELEVATED};
            border-top: 1px solid {SEPARATOR};
            color: {TEXT_MUTED};
            padding: 2px 6px;
            font-size: 12px;
        }}
        QStatusBar QLabel {{
            background: transparent;
            padding: 0 6px;
            color: {TEXT_MUTED};
        }}
        QStatusBar::item {{ border: none; }}

        /* Mac-style thin scrollbars */
        QScrollBar:vertical {{
            background: transparent;
            width: 10px;
            margin: 0;
            border: none;
        }}
        QScrollBar::handle:vertical {{
            background: {BG_HOVER};
            min-height: 24px;
            border-radius: 5px;
            margin: 2px;
        }}
        QScrollBar::handle:vertical:hover {{ background: {BG_PRESSED}; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0;
            background: transparent;
        }}
        QScrollBar:horizontal {{
            background: transparent;
            height: 10px;
            margin: 0;
            border: none;
        }}
        QScrollBar::handle:horizontal {{
            background: {BG_HOVER};
            min-width: 24px;
            border-radius: 5px;
            margin: 2px;
        }}
        QScrollBar::handle:horizontal:hover {{ background: {BG_PRESSED}; }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
            width: 0;
            background: transparent;
        }}
    """


def primary_button_qss() -> str:
    """Modern macOS Sequoia / Tahoe primary button.

    Subtle top-to-bottom gradient (lighter blue at top → core accent at
    bottom) gives the button visual depth like a real Mac NSButton's
    bordered prominent style. Hairline white highlight at the top and a
    darker rim at the bottom add the "raised" effect without needing
    NSVisualEffectView.
    """
    accent  = system_accent()        # #0a84ff
    top     = _shift(accent, 1.18)   # lighter top stop
    hover_t = _shift(accent, 1.30)
    hover_b = _shift(accent, 1.05)
    pressed = _shift(accent, 0.85)
    return f"""
        QPushButton {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {top}, stop:1 {accent});
            border: 1px solid {_shift(accent, 0.88)};
            border-top: 1px solid {hover_t};
            border-radius: 7px;
            padding: 6px 18px;
            color: white;
            font-weight: 600;
            font-size: 13px;
        }}
        QPushButton:hover {{
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {hover_t}, stop:1 {hover_b});
            border: 1px solid {accent};
        }}
        QPushButton:pressed {{
            background: {pressed};
            border: 1px solid {_shift(pressed, 0.85)};
        }}
        QPushButton:disabled {{
            background: {BG_HOVER};
            border: 1px solid {BG_HOVER};
            color: {TEXT_DIM};
        }}
    """


def secondary_button_qss() -> str:
    """Subtle bordered button (Reset, Cancel, Browse…)."""
    return f"""
        QPushButton {{
            background-color: {BG_ELEVATED};
            border: 1px solid {SEPARATOR};
            border-radius: {RADIUS_M}px;
            padding: 6px 14px;
            color: {TEXT};
            font-weight: 500;
            font-size: 13px;
        }}
        QPushButton:hover {{
            background-color: {BG_HOVER};
            border-color: {BG_PRESSED};
        }}
        QPushButton:pressed {{
            background-color: {BG_PRESSED};
        }}
        QPushButton:disabled {{
            color: {TEXT_DIM};
            background-color: {BG};
            border-color: {SEPARATOR};
        }}
    """


def danger_button_qss() -> str:
    return f"""
        QPushButton {{
            background-color: {BG_ELEVATED};
            border: 1px solid {SEPARATOR};
            border-radius: {RADIUS_M}px;
            padding: 6px 14px;
            color: {DANGER};
            font-weight: 500;
        }}
        QPushButton:hover {{
            background-color: {DANGER};
            border-color: {DANGER};
            color: white;
        }}
        QPushButton:pressed {{
            background-color: {_shift(DANGER, 0.85)};
        }}
    """


def record_button_qss(state: str = "idle", height: int = 24) -> str:
    """State-aware styling for the status-bar Record button.

    states:
      'idle'      — neutral secondary (subtle; doesn't grab attention)
      'recording' — filled red (universal "stop" signal)
      'processing'— disabled gray
    """
    if state == "recording":
        return f"""
            QPushButton {{
                background-color: {DANGER};
                border: 1px solid {DANGER};
                border-radius: {RADIUS_M}px;
                padding: 2px 14px;
                font-size: 12px;
                font-weight: 600;
                color: white;
                min-height: {height}px;
                max-height: {height}px;
            }}
            QPushButton:hover {{
                background-color: {_shift(DANGER, 1.10)};
                border-color: {_shift(DANGER, 1.10)};
            }}
            QPushButton:pressed {{
                background-color: {_shift(DANGER, 0.88)};
            }}
        """
    # 'idle' (and fallback for 'processing'; setEnabled(False) handles the look)
    return f"""
        QPushButton {{
            background-color: {BG_HOVER};
            border: 1px solid {SEPARATOR};
            border-radius: {RADIUS_M}px;
            padding: 2px 14px;
            font-size: 12px;
            font-weight: 600;
            color: {TEXT};
            min-height: {height}px;
            max-height: {height}px;
        }}
        QPushButton:hover {{
            background-color: {BG_PRESSED};
            border-color: {BG_PRESSED};
        }}
        QPushButton:pressed {{
            background-color: {SEPARATOR};
        }}
        QPushButton:disabled {{
            background-color: {BG_ELEVATED};
            border-color: {BG_ELEVATED};
            color: {TEXT_MUTED};
        }}
    """


def combo_qss() -> str:
    return f"""
        QComboBox {{
            background-color: {BG_ELEVATED};
            border: 1px solid {SEPARATOR};
            border-radius: {RADIUS_S}px;
            padding: 5px 10px;
            color: {TEXT};
            min-width: 180px;
            font-size: 13px;
        }}
        QComboBox:hover {{ border-color: {system_accent()}; }}
        QComboBox:focus {{ border-color: {system_accent()}; }}
        QComboBox::drop-down {{ border: none; padding-right: 8px; }}
        QComboBox QAbstractItemView {{
            background-color: {BG_ELEVATED};
            border: 1px solid {SEPARATOR};
            border-radius: {RADIUS_S}px;
            selection-background-color: {system_accent()};
            selection-color: white;
            color: {TEXT};
            padding: 4px;
        }}
    """


def line_edit_qss() -> str:
    return f"""
        QLineEdit {{
            background-color: {BG_ELEVATED};
            border: 1px solid {SEPARATOR};
            border-radius: {RADIUS_S}px;
            padding: 6px 10px;
            color: {TEXT};
            selection-background-color: {system_accent()};
            selection-color: white;
        }}
        QLineEdit:focus {{ border-color: {system_accent()}; }}
    """


def spin_qss() -> str:
    return f"""
        QSpinBox, QDoubleSpinBox {{
            background-color: {BG_ELEVATED};
            border: 1px solid {SEPARATOR};
            border-radius: {RADIUS_S}px;
            padding: 5px 10px;
            color: {TEXT};
        }}
        QSpinBox:focus, QDoubleSpinBox:focus {{ border-color: {system_accent()}; }}
    """


def slider_qss() -> str:
    return f"""
        QSlider::groove:horizontal {{
            background: {BG_HOVER};
            height: 4px;
            border-radius: 2px;
        }}
        QSlider::handle:horizontal {{
            background: {system_accent()};
            width: 14px;
            height: 14px;
            margin: -5px 0;
            border-radius: 7px;
        }}
        QSlider::handle:horizontal:hover {{
            background: {accent_hover()};
        }}
        QSlider::sub-page:horizontal {{
            background: {system_accent()};
            border-radius: 2px;
        }}
    """


def group_qss() -> str:
    return f"""
        QGroupBox {{
            background-color: {BG_ELEVATED};
            border: 1px solid {SEPARATOR};
            border-radius: {RADIUS_L}px;
            margin-top: 14px;
            padding: 8px 4px 4px 4px;
            font-weight: 600;
            color: {TEXT};
            font-size: 13px;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            padding: 2px 10px;
            background: transparent;
            color: {TEXT};
        }}
    """


def checkbox_qss() -> str:
    return f"""
        QCheckBox {{ color: {TEXT}; spacing: 8px; }}
        QCheckBox::indicator {{
            width: 16px;
            height: 16px;
            border: 1px solid {BG_PRESSED};
            border-radius: 4px;
            background: {BG_ELEVATED};
        }}
        QCheckBox::indicator:hover {{ border-color: {system_accent()}; }}
        QCheckBox::indicator:checked {{
            background: {system_accent()};
            border-color: {system_accent()};
            image: url(:/qt-project.org/styles/commonstyle/images/standardbutton-apply-16.png);
        }}
    """


def text_edit_qss() -> str:
    return f"""
        QTextEdit {{
            background-color: {BG_ELEVATED};
            border: 1px solid {SEPARATOR};
            border-radius: {RADIUS_M}px;
            color: {TEXT};
            padding: 10px;
            selection-background-color: {system_accent()};
            selection-color: white;
        }}
        QTextEdit:focus {{ border-color: {system_accent()}; }}
    """


def progress_qss() -> str:
    return f"""
        QProgressBar {{
            background-color: {BG_HOVER};
            border: none;
            border-radius: 4px;
            height: 8px;
            text-align: center;
            color: transparent;
        }}
        QProgressBar::chunk {{
            background-color: {system_accent()};
            border-radius: 4px;
        }}
    """


def table_qss() -> str:
    return f"""
        QTableWidget {{
            background-color: {BG};
            border: 1px solid {SEPARATOR};
            border-radius: {RADIUS_M}px;
            gridline-color: {SEPARATOR};
            color: {TEXT};
            selection-background-color: {system_accent()};
            selection-color: white;
        }}
        QHeaderView::section {{
            background-color: {BG_ELEVATED};
            color: {TEXT_MUTED};
            padding: 6px 10px;
            border: none;
            border-bottom: 1px solid {SEPARATOR};
            font-weight: 600;
        }}
        QTableWidget::item {{ padding: 6px; }}
    """
