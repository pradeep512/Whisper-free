"""
Waveform Painter for Dynamic Island Overlay

Custom Qt painter for rendering audio waveform visualization with gradient bars.
Optimized for real-time updates at 30 FPS.

Author: Whisper-Free Project
License: MIT
"""

from PySide6.QtGui import QPainter, QColor, QLinearGradient, QPen, QPainterPath
from PySide6.QtCore import Qt, QRectF, QPointF
from typing import List
import logging

logger = logging.getLogger(__name__)


class WaveformPainter:
    """
    Custom painter for audio waveform visualization.
    Renders vertical bars representing audio levels with gradient fill.

    The waveform uses a cyan-blue gradient (#64b5f6 to #4dd0e1) and
    renders center-aligned bars with rounded corners.

    Example:
        >>> painter = QPainter(widget)
        >>> painter.setRenderHint(QPainter.Antialiasing)
        >>> waveform_data = [0.5, 0.7, 0.3, 0.8, ...]  # 30 values
        >>> WaveformPainter.paint_waveform(
        ...     painter, waveform_data, widget.rect()
        ... )
    """

    @staticmethod
    def paint_waveform(
        painter: QPainter,
        waveform_data: List[float],
        widget_rect,
        bar_count: int = 30,
        bar_width: int = 4,
        bar_spacing: int = 6,
        min_height: int = 5,
        max_height: int = 40
    ) -> None:
        """
        Paint audio waveform bars with gradient fill.

        Args:
            painter: QPainter instance (should have antialiasing enabled)
            waveform_data: List of audio levels (0.0-1.0), typically 30-50 values
            widget_rect: QRect of the containing widget for positioning
            bar_count: Number of bars to render (default 30)
            bar_width: Width of each bar in pixels (default 4)
            bar_spacing: Spacing between bars in pixels (default 6)
            min_height: Minimum bar height in pixels (default 5)
            max_height: Maximum bar height in pixels (default 40)

        The bars are center-aligned horizontally and vertically in the widget.
        Each bar uses a linear gradient from #64b5f6 (top) to #4dd0e1 (bottom).
        Bars have 2px rounded corners for smooth appearance.

        If waveform_data is empty or None, this method returns silently without
        painting anything.

        Performance:
            Optimized for 30 FPS real-time updates. Uses QPainterPath for
            efficient rounded rectangle rendering.
        """
        # Handle empty or invalid data
        if not waveform_data:
            logger.debug("Empty waveform data, skipping paint")
            return

        # Ensure we have enough data, pad with zeros if needed
        data = list(waveform_data)
        if len(data) < bar_count:
            # Pad with zeros
            data.extend([0.0] * (bar_count - len(data)))
        elif len(data) > bar_count:
            # Downsample by taking evenly spaced samples
            step = len(data) / bar_count
            data = [data[int(i * step)] for i in range(bar_count)]

        # Calculate total width of waveform
        total_width = (bar_width * bar_count) + (bar_spacing * (bar_count - 1))

        # Center the waveform horizontally
        widget_width = widget_rect.width()
        widget_height = widget_rect.height()
        start_x = widget_rect.x() + (widget_width - total_width) / 2.0

        # Center vertically (bars grow up and down from center)
        center_y = widget_rect.y() + (widget_height / 2.0)

        # Create gradient for bars (top to bottom: Indigo 50 to Indigo 400)
        gradient = QLinearGradient(0, center_y - max_height / 2,
                                   0, center_y + max_height / 2)
        gradient.setColorAt(0.0, QColor("#E8EAF6"))  # Greyish White (Indigo 50)
        gradient.setColorAt(1.0, QColor("#5C6BC0"))  # Indigo 400

        # Set painter properties
        painter.setBrush(gradient)
        painter.setPen(Qt.NoPen)  # No border on bars

        # Draw each bar
        for i in range(bar_count):
            # Get level for this bar (clamped to 0.0-1.0)
            level = max(0.0, min(1.0, data[i]))

            # Calculate bar height based on level
            # Interpolate between min_height and max_height
            bar_height = min_height + (level * (max_height - min_height))

            # Calculate bar position
            bar_x = start_x + (i * (bar_width + bar_spacing))
            bar_y = center_y - (bar_height / 2.0)

            # Create rounded rectangle path
            bar_rect = QRectF(bar_x, bar_y, bar_width, bar_height)

            # Draw rounded rectangle (2px corner radius)
            path = QPainterPath()
            path.addRoundedRect(bar_rect, 2.0, 2.0)
            painter.fillPath(path, gradient)

    @staticmethod
    def get_waveform_dimensions(
        bar_count: int = 30,
        bar_width: int = 4,
        bar_spacing: int = 6
    ) -> tuple:
        """
        Calculate the total dimensions needed for waveform rendering.

        Args:
            bar_count: Number of bars
            bar_width: Width of each bar in pixels
            bar_spacing: Spacing between bars in pixels

        Returns:
            Tuple of (width, height) in pixels

        Example:
            >>> width, height = WaveformPainter.get_waveform_dimensions()
            >>> print(f"Waveform needs {width}x{height}px")
        """
        total_width = (bar_width * bar_count) + (bar_spacing * (bar_count - 1))
        # Height is determined by max_height parameter in paint_waveform
        # Default max_height is 40, so total height with padding is ~50
        total_height = 50
        return (total_width, total_height)
