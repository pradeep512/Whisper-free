"""
Dynamic Island Overlay for Whisper-Free

macOS Dynamic Island-inspired always-on-top window that provides visual feedback
during voice recording and transcription. Features smooth animations and waveform
visualization.

Inspired by the dynisland project and macOS Dynamic Island.

Author: Whisper-Free Project
License: MIT
"""

from enum import Enum
import math
import os
import time
from PySide6.QtWidgets import QWidget, QApplication, QLabel, QVBoxLayout
from PySide6.QtGui import QPainter, QColor, QPainterPath, QFont, QFontMetrics, QCursor
from PySide6.QtCore import (
    Qt, QTimer, QPropertyAnimation, QRect, QSize, QPoint,
    QEasingCurve, Signal, QParallelAnimationGroup, Property, QEvent
)
from typing import List, Optional, Tuple
import logging

from app.ui.waveform_painter import WaveformPainter

logger = logging.getLogger(__name__)


class OverlayMode(Enum):
    """
    Overlay display modes with associated dimensions and behavior.

    State Flow:
        HIDDEN → MINIMAL (app ready)
        MINIMAL → LISTENING (recording starts)
        LISTENING → PROCESSING (recording stops)
        PROCESSING → RESULT (transcription complete)
        RESULT → MINIMAL (auto-dismiss after 2.5s)
        MINIMAL → COPIED (user copies text)
        COPIED → MINIMAL (auto-dismiss after 1.5s)
    """
    HIDDEN = 0      # Invisible, no space
    MINIMAL = 1     # Small "Ready" indicator
    LISTENING = 2   # Expanded with waveform
    PROCESSING = 3  # Medium size with spinner
    RESULT = 4      # Large with transcript preview
    COPIED = 5      # Medium "Copied!" confirmation
    STATUS = 6      # interactive info (Model, VRAM, etc.)


class DynamicIslandOverlay(QWidget):
    """
    Always-on-top overlay window with Dynamic Island animations.

    Features:
        - Frameless, translucent window with rounded corners
        - Smooth 600ms animations between modes
        - Real-time waveform visualization during recording
        - Auto-dismiss for temporary states
        - Multi-monitor support (defaults to primary screen)
        - Thread-safe mode transitions

    Window Properties:
        - Always on top of all windows
        - Does not accept focus (non-intrusive)
        - Translucent background with rounded corners
        - Positioned at screen top-center

    Example:
        >>> app = QApplication([])
        >>> overlay = DynamicIslandOverlay()
        >>> overlay.set_mode(OverlayMode.MINIMAL)
        >>> overlay.show()
    """

    # Signals
    mode_changed = Signal(OverlayMode)
    cancel_requested = Signal()  # User clicked 'X'
    stop_requested = Signal()    # User clicked 'Stop' button

    # Mode configurations: (width, height, opacity)
    MODE_CONFIGS = {
        OverlayMode.HIDDEN: (0, 0, 0.0),
        OverlayMode.HIDDEN: (0, 0, 0.0),
        OverlayMode.MINIMAL: (30, 30, 0.4),     # Tiny dot when idle
        OverlayMode.LISTENING: (320, 50, 1.0),  # Compact recording bar
        OverlayMode.PROCESSING: (200, 50, 0.9), # Compact processing pill
        OverlayMode.RESULT: (600, 160, 1.0),    # Taller for better text fit
        OverlayMode.COPIED: (200, 50, 0.9),
        OverlayMode.STATUS: (300, 100, 0.95),   # Info card
    }

    def __init__(self):
        """
        Initialize overlay with X11 window flags and animations.

        Sets up:
            - Frameless, always-on-top window
            - Translucent background
            - Animation system
            - Auto-dismiss timers
        """
        super().__init__()

        # State
        self._mode = OverlayMode.HIDDEN
        self._waveform_data: List[float] = []
        self._result_text = ""
        self._result_language = ""  # New: Store detected language
        self._target_geometry = QRect(0, 0, 0, 0)
        self._position_setting = "top-center"   # Default to top-center
        self._monitor_setting = 0
        self._auto_dismiss_ms = 1000            # Default auto-dismiss (1 second)
        self._content_opacity = 0.0             # Use paint-based opacity (Wayland-safe)
        
        # Status info
        self._model_name = "Unknown"
        self._device_name = "CPU"
        self._vram_usage = "0 MB"

        # Animation
        self._geometry_animation: Optional[QPropertyAnimation] = None
        self._opacity_animation: Optional[QPropertyAnimation] = None
        self._animation_group: Optional[QParallelAnimationGroup] = None

        # Timers
        self._auto_dismiss_timer = QTimer()
        self._auto_dismiss_timer.setSingleShot(True)
        self._auto_dismiss_timer.timeout.connect(self._on_auto_dismiss)

        # Animation timer (30 FPS) for waveform and UI animations
        self._animation_timer = QTimer()
        self._animation_timer.timeout.connect(self._on_animation_tick)
        
        # Blink timer for recording indicator
        self._blink_timer = QTimer()
        self._blink_timer.setInterval(800)  # 800ms blink cycle
        self._blink_timer.timeout.connect(self._on_blink_tick)
        self._blink_state = True
        
        # Button geometries (calculated in paint)
        self._copy_btn_rect: Optional[QRect] = None
        self._cancel_btn_rect: Optional[QRect] = None
        self._stop_btn_rect: Optional[QRect] = None

        # Setup window properties
        self._setup_window()

        # Initialize in hidden state
        self.setGeometry(0, 0, 0, 0)

        logger.info("DynamicIslandOverlay initialized")

    def _setup_window(self) -> None:
        """
        Configure window flags and attributes for always-on-top overlay.

        Sets:
            - Frameless window
            - Always on top
            - Tool window (needed for positioning on Wayland)
            - Does not accept focus
            - Translucent background

        On Wayland, Qt.Tool is required so the compositor allows client-side
        positioning. Without it, Mutter treats the window as a top-level and
        centers it. To prevent Mutter from auto-hiding the Tool window during
        geometry changes, we skip geometry animation on Wayland and set
        geometry directly instead.
        """
        self._is_wayland = os.environ.get('XDG_SESSION_TYPE', '') == 'wayland'

        flags = (
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool |
            Qt.WindowDoesNotAcceptFocus
        )
        if self._is_wayland:
            # Try to bypass the compositor so client-side positioning works.
            # Some compositors may ignore this, but it helps on GNOME in practice.
            flags |= Qt.BypassWindowManagerHint
        self.setWindowFlags(flags)

        # Enable mouse tracking for hover effects
        self.setMouseTracking(True)
        # Enable translucent background
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        # Disable focus but allow mouse input
        self.setFocusPolicy(Qt.NoFocus)

        logger.debug("Window properties configured")

    def set_mode(self, mode: OverlayMode) -> None:
        """
        Change overlay mode with smooth animation.

        Args:
            mode: Target mode to transition to

        The transition includes:
            - Animated resize (600ms, OutCubic easing)
            - Animated opacity change
            - Auto-dismiss timer for RESULT and COPIED modes
            - Waveform updates for LISTENING mode

        Thread Safety:
            This method is thread-safe and can be called from any thread.
            Qt will automatically marshal the call to the UI thread.

        Example:
            >>> overlay.set_mode(OverlayMode.LISTENING)
            >>> # Overlay smoothly expands to listening mode
        """
        if self._mode == mode:
            logger.debug(f"Already in {mode.name} mode, skipping transition")
            return

        old_mode = self._mode
        self._mode = mode

        logger.info(f"Mode transition: {old_mode.name} → {mode.name}")

        # Stop auto-dismiss timer from previous mode
        if self._auto_dismiss_timer.isActive():
            self._auto_dismiss_timer.stop()

        # Stop animation timer
        if self._animation_timer.isActive():
            self._animation_timer.stop()

        # Get target configuration
        target_width, target_height, target_opacity = self.MODE_CONFIGS[mode]

        # Calculate target geometry
        target_geometry = self._calculate_geometry(target_width, target_height)

        if self._is_wayland:
            # On Wayland: set geometry directly (no animation) to avoid
            # Mutter auto-hiding the Tool window during geometry transitions.
            # Only animate opacity for visual smoothness.
            if mode == OverlayMode.HIDDEN:
                self._animate_opacity_only(target_opacity, on_done=self.hide)
            else:
                self._apply_geometry_wayland(target_geometry)
                self._animate_opacity_only(target_opacity)
                self.show()
                self.raise_()
        else:
            # On X11: full geometry + opacity animation
            if old_mode == OverlayMode.HIDDEN:
                start_geo = QRect(target_geometry)
                start_geo.setWidth(0)
                start_geo.setHeight(0)
                start_geo.moveCenter(target_geometry.center())
                self.setGeometry(start_geo)

            self._animate_to_geometry(target_geometry, target_opacity)

        # Start mode-specific timers
        if mode == OverlayMode.RESULT:
            self._auto_dismiss_timer.start(self._auto_dismiss_ms)
        elif mode == OverlayMode.COPIED:
            self._auto_dismiss_timer.start(self._auto_dismiss_ms)
        elif mode == OverlayMode.LISTENING:
            # Start animation timer for waveform
            self._animation_timer.start(33)
            # Start blink timer
            self._blink_timer.start()
            self._blink_state = True
        elif mode == OverlayMode.PROCESSING:
             # Start animation timer for spinner
             self._animation_timer.start(33)

        # Emit signal
        self.mode_changed.emit(mode)

        # Trigger repaint
        self.update()

    def set_position(self, position: str = "top-center", monitor_index: int = 0) -> None:
        """
        Set overlay position on screen.

        Args:
            position: "top-left", "top-center", "top-right",
                     "bottom-left", "bottom-center", "bottom-right"
            monitor_index: Monitor index (0 = primary/default)
        """
        self._position_setting = position
        self._monitor_setting = monitor_index

        # Recalculate geometry for current mode
        width, height, _ = self.MODE_CONFIGS[self._mode]
        target_geometry = self._calculate_geometry(width, height)

        # Apply immediately if visible
        if self.isVisible():
            if self._is_wayland:
                self._apply_geometry_wayland(target_geometry)
                self.update()
            else:
                self._animate_to_geometry(target_geometry, self._content_opacity)
        else:
            self.setGeometry(target_geometry)

    def _calculate_geometry(self, width: int, height: int) -> QRect:
        """
        Calculate geometry based on position setting and monitor.

        Supports positions: top-left, top-center, top-right,
                           bottom-left, bottom-center, bottom-right
        """
        screens = QApplication.screens()
        if not screens:
            return QRect(0, 0, width, height)

        # Get target screen
        if 0 <= self._monitor_setting < len(screens):
            screen = screens[self._monitor_setting]
        else:
            screen = QApplication.primaryScreen()

        screen_geo = screen.availableGeometry()  # Excludes panels/taskbars

        # Padding from screen edges
        padding_x = 20
        padding_y = 8

        # Horizontal position
        if "left" in self._position_setting:
            x = screen_geo.x() + padding_x
        elif "right" in self._position_setting:
            x = screen_geo.x() + screen_geo.width() - width - padding_x
        else:  # center
            x = screen_geo.x() + (screen_geo.width() - width) // 2

        # Vertical position
        if "bottom" in self._position_setting:
            y = screen_geo.y() + screen_geo.height() - height - padding_y
        else:  # top
            y = screen_geo.y() + padding_y

        return QRect(x, y, width, height)

    def set_auto_dismiss_ms(self, ms: int) -> None:
        """
        Set the auto-dismiss delay for RESULT and COPIED modes.

        Args:
            ms: Delay in milliseconds (minimum 500ms)
        """
        self._auto_dismiss_ms = max(500, ms)
        logger.debug(f"Auto-dismiss set to {self._auto_dismiss_ms}ms")

    def _calculate_centered_geometry(self, width: int, height: int) -> QRect:
        """Deprecated: use _calculate_geometry instead."""
        return self._calculate_geometry(width, height)

    def _animate_to_geometry(self, target_geometry: QRect, target_opacity: float, duration: int = 600, easing: QEasingCurve.Type = QEasingCurve.OutCubic) -> None:
        """
        Animate overlay to target geometry and opacity.

        Args:
            target_geometry: Target position and size
            target_opacity: Target opacity (0.0-1.0)
            duration: Animation duration in ms
            easing: Animation curve type
        """
        # Stop any running animations
        if self._animation_group and self._animation_group.state() == QParallelAnimationGroup.Running:
            self._animation_group.stop()

        # Create animation group
        self._animation_group = QParallelAnimationGroup()

        # Geometry animation
        self._geometry_animation = QPropertyAnimation(self, b"geometry")
        self._geometry_animation.setDuration(duration)
        self._geometry_animation.setStartValue(self.geometry())
        self._geometry_animation.setEndValue(target_geometry)
        self._geometry_animation.setEasingCurve(easing)

        # Opacity animation (paint-based, Wayland-safe)
        self._opacity_animation = QPropertyAnimation(self, b"contentOpacity")
        self._opacity_animation.setDuration(duration)
        self._opacity_animation.setStartValue(self._content_opacity)
        self._opacity_animation.setEndValue(target_opacity)
        self._opacity_animation.setEasingCurve(easing)

        # Add to group
        self._animation_group.addAnimation(self._geometry_animation)
        self._animation_group.addAnimation(self._opacity_animation)

        # Start animation
        self._animation_group.start()

        # Show window if hidden
        if not self.isVisible() and self._mode != OverlayMode.HIDDEN:
            self.show()
        elif self._mode == OverlayMode.HIDDEN:
            # Hide after animation completes
            self._animation_group.finished.connect(self.hide)

    def _animate_opacity_only(self, target_opacity: float, duration: int = 300, on_done=None) -> None:
        """
        Animate only opacity (used on Wayland where geometry animation
        causes the compositor to auto-hide Tool windows).
        """
        if self._animation_group and self._animation_group.state() == QParallelAnimationGroup.Running:
            self._animation_group.stop()

        self._opacity_animation = QPropertyAnimation(self, b"contentOpacity")
        self._opacity_animation.setDuration(duration)
        self._opacity_animation.setStartValue(self._content_opacity)
        self._opacity_animation.setEndValue(target_opacity)
        self._opacity_animation.setEasingCurve(QEasingCurve.OutCubic)

        if on_done:
            self._opacity_animation.finished.connect(on_done)

        self._opacity_animation.start()

    def _apply_geometry_wayland(self, target_geometry: QRect) -> None:
        """
        Best-effort positioning on Wayland (GNOME Mutter).
        Re-apply geometry after show to improve compositor compliance.
        """
        self.setGeometry(target_geometry)
        handle = self.windowHandle()
        if handle:
            handle.setPosition(target_geometry.topLeft())
        # Re-apply after the surface is mapped
        QTimer.singleShot(0, lambda tg=QRect(target_geometry): self._apply_geometry_wayland_once(tg))
        QTimer.singleShot(50, lambda tg=QRect(target_geometry): self._apply_geometry_wayland_once(tg))

    def _apply_geometry_wayland_once(self, target_geometry: QRect) -> None:
        """Single-shot geometry set used by _apply_geometry_wayland."""
        self.setGeometry(target_geometry)
        handle = self.windowHandle()
        if handle:
            handle.setPosition(target_geometry.topLeft())

    def _get_content_opacity(self) -> float:
        return self._content_opacity

    def _set_content_opacity(self, value: float) -> None:
        self._content_opacity = max(0.0, min(1.0, float(value)))
        self.update()

    contentOpacity = Property(float, _get_content_opacity, _set_content_opacity)

    def update_waveform(self, levels: List[float]) -> None:
        """
        Update waveform data for LISTENING mode.

        Args:
            levels: List of 30-50 float values (0.0-1.0) representing audio levels

        The waveform is updated in real-time during recording. Values should
        represent RMS audio levels normalized to the 0.0-1.0 range.

        This method is thread-safe and can be called from the audio thread.

        Example:
            >>> # From audio recording thread
            >>> levels = recorder.get_waveform_data()
            >>> overlay.update_waveform(levels)
        """
        self._waveform_data = list(levels) if levels else []

        # Only repaint if in LISTENING mode
        if self._mode == OverlayMode.LISTENING:
            self.update()

    def set_result_text(self, text: str, language: str = "") -> None:
        """
        Show transcription result with auto-dismiss.

        Args:
            text: Transcription text to display
            language: Detected language code or name (optional)
        """
        # No truncation - let it wrap
        self._result_text = text
        self._result_language = language
        
        # Calculate needed height? For now use fixed RESULT mode size
        # Ideally we'd measure text here and adjust MODE_CONFIGS logic
        # But fixed size with word wrap should cover most short commands/sentences

        # Transition to result mode (this starts auto-dismiss timer)
        self.set_mode(OverlayMode.RESULT)

        logger.debug(f"Showing result: {self._result_text}")

    def show_copied_confirmation(self) -> None:
        """
        Show 'Copied!' confirmation message.

        Transitions to COPIED mode and auto-dismisses after 1.5 seconds,
        returning to MINIMAL mode.

        Example:
            >>> # User presses Ctrl+C
            >>> overlay.show_copied_confirmation()
        """
        self.set_mode(OverlayMode.COPIED)
        logger.debug("Showing copied confirmation")

    def set_status_info(self, model: str, device: str, vram: str) -> None:
        """Update status information for STATUS mode."""
        self._model_name = model
        self._device_name = device
        self._vram_usage = vram
        # Repaint if currently showing status
        if self._mode == OverlayMode.STATUS:
            self.update()

    def _on_auto_dismiss(self) -> None:
        """
        Handle auto-dismiss timer timeout.

        Transitions back to MINIMAL mode from temporary states
        (RESULT or COPIED).
        """
        logger.debug(f"Auto-dismiss from {self._mode.name}")
        self.set_mode(OverlayMode.HIDDEN)

    def _on_animation_tick(self) -> None:
        """
        Handle 30 FPS animation tick.
        Updates waveform or processing animations.
        """
        if self._mode in [OverlayMode.LISTENING, OverlayMode.PROCESSING]:
            self.update()

    def paintEvent(self, event):
        """
        Custom painting for rounded background and mode-specific content.

        Renders:
            - Rounded rectangle background (50px border-radius)
            - Mode-specific content (text, waveform, spinner)
            - Semi-transparent border

        The background color is rgba(0, 0, 0, 217) with a subtle white border.
        All rendering uses antialiasing for smooth appearance.
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Get widget dimensions
        width = self.width()
        height = self.height()

        # Don't paint if hidden
        if width == 0 or height == 0 or self._content_opacity <= 0.0:
            return

        # Apply overall fade without relying on window opacity (Wayland-safe)
        painter.setOpacity(self._content_opacity)

        # Draw rounded background
        self._paint_background(painter, width, height)

        # Draw mode-specific content
        if self._mode == OverlayMode.MINIMAL:
            self._paint_minimal(painter, width, height)
        elif self._mode == OverlayMode.LISTENING:
            self._paint_listening(painter, width, height)
        elif self._mode == OverlayMode.PROCESSING:
            self._paint_processing(painter, width, height)
        elif self._mode == OverlayMode.RESULT:
            self._paint_result(painter, width, height)
        elif self._mode == OverlayMode.COPIED:
            self._paint_copied(painter, width, height)
        elif self._mode == OverlayMode.STATUS:
            self._paint_status(painter, width, height)

    def _paint_background(self, painter: QPainter, width: int, height: int) -> None:
        """
        Paint rounded rectangle background with border.

        Args:
            painter: QPainter instance
            width: Widget width
            height: Widget height

        Background:
            - Fill: rgba(0, 0, 0, 217) [black with 85% opacity]
            - Border: 1px rgba(255, 255, 255, 0.1) [white with 10% opacity]
            - Border radius: 50px (very rounded)
        """
        # Create rounded rectangle path
        path = QPainterPath()
        path.addRoundedRect(0, 0, width, height, 16, 16) # Reduced radius from 50 to 16

        # Fill background
        painter.fillPath(path, QColor(0, 0, 0, 217))

        # Draw border
        border_color = QColor(255, 255, 255, 26)  # 10% opacity = 26/255
        painter.setPen(border_color)
        painter.drawPath(path)

    def _paint_minimal(self, painter: QPainter, width: int, height: int) -> None:
        """Paint MINIMAL mode: Tiny confused dot."""
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 255, 255, 100))
        
        # Draw small circle in center
        radius = 6
        center = QPoint(width // 2, height // 2)
        painter.drawEllipse(center, radius, radius)

    def _paint_listening(self, painter: QPainter, width: int, height: int) -> None:
        """Paint LISTENING mode: Close Btn | Waveform | Stop Btn."""
        
        # 1. Close/Cancel Button (Left)
        # -----------------------------
        btn_size = 24  # Slightly smaller
        padding_x = 10 # Reduced padding
        center_y = height // 2
        
        self._cancel_btn_rect = QRect(padding_x, center_y - btn_size // 2, btn_size, btn_size)
        
        # Draw Circle Background (Gray)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(128, 128, 128, 150))
        painter.drawEllipse(self._cancel_btn_rect)
        
        # Draw 'X' Icon
        painter.setPen(QColor(255, 255, 255))
        painter.setFont(QFont("Inter", 12, QFont.Bold))
        painter.drawText(self._cancel_btn_rect, Qt.AlignCenter, "×")

        # 2. Stop Button (Right)
        # ----------------------
        stop_btn_x = width - padding_x - btn_size
        self._stop_btn_rect = QRect(stop_btn_x, center_y - btn_size // 2, btn_size, btn_size)

        # Draw Circle Background (Red)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 59, 48)) # Start with Red
        painter.drawEllipse(self._stop_btn_rect)
        
        # Draw Stop Square
        square_size = 8
        square_rect = QRect(
            stop_btn_x + (btn_size - square_size) // 2,
            center_y - square_size // 2,
            square_size,
            square_size
        )
        painter.setBrush(QColor(255, 255, 255)) # White
        painter.drawRoundedRect(square_rect, 2, 2)

        # 3. Waveform (Center)
        # --------------------
        # Space between buttons (tight gap)
        start_x = self._cancel_btn_rect.right() + 6
        end_x = self._stop_btn_rect.left() - 6
        waveform_width = end_x - start_x
        
        if self._waveform_data and waveform_width > 0:
            waveform_rect = QRect(start_x, 10, waveform_width, height - 20)
            WaveformPainter.paint_waveform(
                painter,
                self._waveform_data,
                waveform_rect,
                bar_count=22, # Reduced bar count to fit smaller width
                bar_width=4,
                bar_spacing=5,
                min_height=4,
                max_height=height - 20
            )

    def _paint_processing(self, painter: QPainter, width: int, height: int) -> None:
        """Paint PROCESSING mode: Animated 3-dot pulse."""
        
        # Center coordinates
        center_x = width // 2
        center_y = height // 2
        
        # Dot configuration
        dot_radius = 4
        spacing = 14
        
        # Current time for animation phase
        t = time.time() * 5 # Speed multiplier
        
        painter.setPen(Qt.NoPen)
        
        # Draw 3 dots
        for i in range(3):
            # Calculate opacity based on sine wave with offset for each dot
            # Result is 0.2 to 1.0 opacity
            opacity = 0.2 + 0.8 * (0.5 * (1 + math.sin(t - i * 0.8)))
            
            x = center_x + (i - 1) * spacing
            
            painter.setBrush(QColor(255, 255, 255, int(255 * opacity)))
            painter.drawEllipse(QPoint(x, center_y), dot_radius, dot_radius)

    def _paint_result(self, painter: QPainter, width: int, height: int) -> None:
        """Paint RESULT mode: Transcript + Copy Button."""
        
        # 1. Background Content Area
        # --------------------------
        content_rect = QRect(20, 20, width - 40, height - 40)
        
        # Label "Transcription"
        painter.setPen(QColor(255, 255, 255, 150))
        painter.setFont(QFont("Inter", 10, QFont.Medium))
        painter.drawText(content_rect, Qt.AlignLeft | Qt.AlignTop, "Transcription")
        
        # Label "Language" (Top Right)
        if self._result_language:
            painter.drawText(content_rect, Qt.AlignRight | Qt.AlignTop, self._result_language.title())
        
        # 2. Main Text
        # ------------
        text_rect = QRect(20, 45, width - 40, height - 85) # Reserve space for button
        painter.setPen(QColor(255, 255, 255))
        painter.setFont(QFont("Inter", 14, QFont.Normal))
        
        # Draw text with ellipsis if it fails to fit
        option =  Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap
        painter.drawText(text_rect, option, self._result_text)

        # 3. Copy Button (Bottom Right, Pill Styling)
        # -------------------------------------------
        btn_width = 90
        btn_height = 32
        btn_x = width - btn_width - 20
        btn_y = height - btn_height - 20
        
        self._copy_btn_rect = QRect(btn_x, btn_y, btn_width, btn_height)
        
        # Determine if hovered (requires mouse tracking, skipping for now)
        # Button Gradient Background
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 255, 255, 30)) # Translucent white
        painter.drawRoundedRect(self._copy_btn_rect, 16, 16)
        
        # Icon + Text
        painter.setPen(QColor(255, 255, 255))
        painter.setFont(QFont("Inter", 12, QFont.Bold))
        painter.drawText(self._copy_btn_rect, Qt.AlignCenter, "Copy")
        
        # Optional: Add Copy Icon (simple rects)
        icon_size = 12
        icon_x = btn_x + 15
        icon_y = btn_y + (btn_height - icon_size) // 2
        # (Skipping complicated icon drawing for cleanliness)

    def _paint_copied(self, painter: QPainter, width: int, height: int) -> None:
        """Paint COPIED mode: 'Copied!' confirmation."""
        self._paint_text(painter, "Copied!", width, height)

    def _paint_status(self, painter: QPainter, width: int, height: int) -> None:
        """Paint STATUS mode: Model and Device info."""
        # Title
        painter.setPen(QColor(255, 255, 255))
        painter.setFont(QFont("Inter", 12, QFont.Bold))
        painter.drawText(QRect(20, 15, width-40, 20), Qt.AlignLeft, "Whisper-Free")
        
        # Details
        painter.setFont(QFont("Inter", 11, QFont.Normal))
        painter.setPen(QColor(255, 255, 255, 200))
        
        details = f"Model: {self._model_name}\nDevice: {self._device_name}\nVRAM: {self._vram_usage}"
        painter.drawText(QRect(20, 40, width-40, 60), Qt.AlignLeft, details)


    def _paint_text(
        self,
        painter: QPainter,
        text: str,
        width: int,
        height: int,
        font_size: int = 16,
        rect: Optional[QRect] = None,
        align: int = Qt.AlignCenter
    ) -> None:
        """
        Paint centered text with standard styling.

        Args:
            painter: QPainter instance
            text: Text to display
            width: Widget width
            height: Widget height
            font_size: Font size in pixels (default 16)
            rect: Custom bounding rect
            align: Alignment flags
        """
        painter.setPen(QColor(255, 255, 255))
        font = QFont("Inter", font_size, QFont.Medium)
        painter.setFont(font)

        # Draw centered text with padding
        target_rect = rect if rect else QRect(16, 8, width - 32, height - 16)
        
        # Use elided text if no wrapping requested and it overflows?
        # For now, just draw.
        painter.drawText(target_rect, align, text)

    def mousePressEvent(self, event):
        """Handle mouse clicks."""
        if event.button() != Qt.LeftButton:
            return

        pos = event.pos()

        # LISTENING Mode Interactions
        if self._mode == OverlayMode.LISTENING:
            # Check Cancel Button
            if self._cancel_btn_rect and self._cancel_btn_rect.contains(pos):
                self.cancel_requested.emit()
                event.accept()
                return
            
            # Check Stop Button
            if self._stop_btn_rect and self._stop_btn_rect.contains(pos):
                self.stop_requested.emit()
                event.accept()
                return

        # RESULT Mode Interactions
        elif self._mode == OverlayMode.RESULT:
            if self._copy_btn_rect and self._copy_btn_rect.contains(pos):
                QApplication.clipboard().setText(self._result_text)
                self.show_copied_confirmation()
                event.accept()
                return

        # MINIMAL Mode -> Toggle Status
        elif self._mode == OverlayMode.MINIMAL:
            self.set_mode(OverlayMode.STATUS)
            self._auto_dismiss_timer.start(4000)
            event.accept()
            return
            
        # STATUS Mode -> Toggle Minimal
        elif self._mode == OverlayMode.STATUS:
            self.set_mode(OverlayMode.MINIMAL)
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Standard mouse move."""
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """Standard mouse release."""
        super().mouseReleaseEvent(event)

    def _on_blink_tick(self) -> None:
        """Toggle blink state."""
        self._blink_state = not self._blink_state
        if self._mode == OverlayMode.LISTENING:
            self.update()

    @property
    def mode(self) -> OverlayMode:
        """Get current overlay mode."""
        return self._mode

    @property
    def waveform_data(self) -> List[float]:
        """Get current waveform data."""
        return self._waveform_data.copy()

    def __repr__(self) -> str:
        """String representation of overlay state."""
        return f"DynamicIslandOverlay(mode={self._mode.name}, visible={self.isVisible()})"
