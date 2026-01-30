"""
HistoryPanel - Transcription history display

Displays transcription history with:
- Search/filter functionality
- Export options (TXT, JSON)
- Copy to clipboard
- Scrollable list with modern card design
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit, QLabel,
    QFrame, QMessageBox, QFileDialog, QApplication, QScrollArea,
    QGridLayout, QSizePolicy
)
from PySide6.QtCore import Signal, Qt, QSize, QEvent, QTimer
from PySide6.QtGui import QFont
from datetime import datetime
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class HistoryPanel(QWidget):
    """
    Displays transcription history with search and export.
    """

    # Signals
    text_copied = Signal(str)  # Emitted when text is copied

    def __init__(self, db_manager):
        """
        Initialize history panel

        Args:
            db_manager: DatabaseManager instance
        """
        super().__init__()
        self.db = db_manager
        self.history_widgets = []  # Store widget instances
        self.current_transcriptions = []
        self.current_filter = None  # Filter by source_type (None, 'microphone', 'file')
        self._pending_reload = False
        self.current_offset = 0  # Pagination offset
        self.page_size = 50  # Items per page
        self.has_more_items = True  # Whether there are more items to load

        # Debounce timer to prevent rapid reloads
        self.reload_timer = QTimer()
        self.reload_timer.setSingleShot(True)
        self.reload_timer.setInterval(300)  # 300ms debounce
        self.reload_timer.timeout.connect(self._perform_reload)

        self._setup_ui()

        # Install event filter for resize handling
        self.installEventFilter(self)

        logger.info("HistoryPanel initialized")

    def _setup_ui(self):
        """Create search bar, list, export buttons"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Header
        header_label = QLabel("Transcription History")
        header_label.setStyleSheet("font-size: 24px; font-weight: bold; color: #ffffff;")
        layout.addWidget(header_label)

        # Search bar
        search_layout = QHBoxLayout()
        search_layout.setSpacing(8)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search transcriptions...")
        self.search_input.textChanged.connect(self.search)
        self.search_input.setStyleSheet("""
            QLineEdit {
                background-color: #2d2d2d;
                border: 1px solid #3d3d3d;
                border-radius: 6px;
                padding: 10px 12px;
                font-size: 14px;
                color: #ffffff;
            }
            QLineEdit:focus {
                border: 1px solid #0078d4;
            }
        """)

        clear_btn = QPushButton("×")
        clear_btn.setFixedSize(40, 40)
        clear_btn.clicked.connect(self._clear_search)
        clear_btn.setStyleSheet("""
            QPushButton {
                background-color: #2d2d2d;
                border: 1px solid #3d3d3d;
                border-radius: 6px;
                font-size: 20px;
                font-weight: bold;
                color: #888888;
            }
            QPushButton:hover {
                background-color: #3d3d3d;
                color: #ffffff;
            }
            QPushButton:pressed {
                background-color: #4d4d4d;
            }
        """)

        search_layout.addWidget(self.search_input, 1)
        search_layout.addWidget(clear_btn)
        layout.addLayout(search_layout)

        # Filter buttons
        filter_layout = QHBoxLayout()
        filter_layout.setSpacing(8)

        filter_label = QLabel("Filter:")
        filter_label.setStyleSheet("color: #888888; font-size: 12px;")
        filter_layout.addWidget(filter_label)

        self.filter_all_btn = QPushButton("All")
        self.filter_all_btn.setCheckable(True)
        self.filter_all_btn.setChecked(True)
        self.filter_all_btn.clicked.connect(lambda: self._set_filter(None))

        self.filter_ptt_btn = QPushButton("🎤 Push-to-Talk")
        self.filter_ptt_btn.setCheckable(True)
        self.filter_ptt_btn.clicked.connect(lambda: self._set_filter('microphone'))

        self.filter_file_btn = QPushButton("📁 Files")
        self.filter_file_btn.setCheckable(True)
        self.filter_file_btn.clicked.connect(lambda: self._set_filter('file'))

        # Style filter buttons
        filter_btn_style = """
            QPushButton {
                background-color: #2d2d2d;
                border: 1px solid #3d3d3d;
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 12px;
                color: #888888;
            }
            QPushButton:hover {
                background-color: #3d3d3d;
                color: #ffffff;
            }
            QPushButton:checked {
                background-color: #0078d4;
                border: 1px solid #0078d4;
                color: #ffffff;
            }
        """
        self.filter_all_btn.setStyleSheet(filter_btn_style)
        self.filter_ptt_btn.setStyleSheet(filter_btn_style)
        self.filter_file_btn.setStyleSheet(filter_btn_style)

        filter_layout.addWidget(self.filter_all_btn)
        filter_layout.addWidget(self.filter_ptt_btn)
        filter_layout.addWidget(self.filter_file_btn)
        filter_layout.addStretch()
        layout.addLayout(filter_layout)

        # History Grid Area
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: transparent;
            }
            QScrollArea > QWidget > QWidget {
                background: transparent;
            }
            QScrollBar:vertical {
                background: #2d2d2d;
                width: 10px;
                margin: 0px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical {
                background: #4d4d4d;
                min-height: 20px;
                border-radius: 5px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)
        
        self.grid_container = QWidget()
        self.grid_container.setStyleSheet("background-color: transparent;")
        self.grid_layout = QGridLayout(self.grid_container)
        self.grid_layout.setSpacing(12)
        self.grid_layout.setContentsMargins(0, 0, 16, 0) # Right padding for scrollbar
        self.grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        self.scroll_area.setWidget(self.grid_container)
        layout.addWidget(self.scroll_area, 1)

        # Footer buttons
        footer_layout = QHBoxLayout()
        footer_layout.setSpacing(8)

        # Clear History Button
        clear_history_btn = QPushButton("Clear History")
        clear_history_btn.clicked.connect(self._confirm_clear_history)
        clear_history_btn.setStyleSheet("""
            QPushButton {
                background-color: #2d2d2d;
                border: 1px solid #d32f2f;
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 12px;
                color: #ff5252;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #d32f2f;
                color: #ffffff;
            }
            QPushButton:pressed {
                background-color: #b71c1c;
            }
        """)

        # Export buttons
        export_txt_btn = QPushButton("Export Text")
        export_txt_btn.clicked.connect(self.export_to_txt)
        export_txt_btn.setStyleSheet(self._button_style())

        export_json_btn = QPushButton("Export JSON")
        export_json_btn.clicked.connect(self.export_to_json)
        export_json_btn.setStyleSheet(self._button_style())

        # Load More button
        self.load_more_btn = QPushButton("Load More...")
        self.load_more_btn.clicked.connect(self._load_more)
        self.load_more_btn.setVisible(False)  # Hidden initially
        self.load_more_btn.setStyleSheet("""
            QPushButton {
                background-color: #0078d4;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-size: 13px;
                color: #ffffff;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #005a9e;
            }
            QPushButton:pressed {
                background-color: #004578;
            }
        """)

        footer_layout.addWidget(clear_history_btn)
        footer_layout.addWidget(self.load_more_btn)
        footer_layout.addStretch()
        footer_layout.addWidget(export_txt_btn)
        footer_layout.addWidget(export_json_btn)
        layout.addLayout(footer_layout)

    def _button_style(self) -> str:
        """Get standard button stylesheet"""
        return """
            QPushButton {
                background-color: #2d2d2d;
                border: 1px solid #3d3d3d;
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 12px;
                color: #cccccc;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #0078d4;
                border-color: #0078d4;
            }
            QPushButton:pressed {
                background-color: #005a9e;
            }
        """

    def _clear_search(self):
        """Clear search input"""
        self.search_input.clear()

    def _confirm_clear_history(self):
        """Show confirmation dialog to clear history"""
        reply = QMessageBox.question(
            self,
            "Clear History",
            "Are you sure you want to delete ALL transcription history?\nThis action cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                count = self.db.clear_history()
                self.load_history() # Refresh UI
                QMessageBox.information(
                    self,
                    "History Cleared",
                    f"Successfully deleted {count} transcriptions."
                )
            except Exception as e:
                logger.error(f"Failed to clear history: {e}")
                QMessageBox.critical(
                    self,
                    "Error",
                    f"Failed to clear history:\n{str(e)}"
                )

    def load_history(self, reset: bool = True):
        """
        Request a history reload (debounced to prevent rapid updates).

        Args:
            reset: If True, reset pagination to first page
        """
        if reset:
            self.current_offset = 0
        self._pending_reload = True
        self.reload_timer.start()  # Restart timer (resets if already running)

    def _perform_reload(self):
        """
        Actually reload history after debounce period.
        Loads items based on current pagination state.
        """
        if not self._pending_reload:
            return

        self._pending_reload = False

        try:
            # Fetch transcriptions from database with pagination
            transcriptions = self.db.get_recent_transcriptions(
                limit=self.page_size,
                offset=self.current_offset
            )

            # Check if there are more items
            total_count = self.db.get_transcription_count()
            self.has_more_items = (self.current_offset + self.page_size) < total_count

            # Apply source type filter if set
            if self.current_filter:
                transcriptions = [
                    t for t in transcriptions
                    if t.get('source_type') == self.current_filter
                ]

            # If this is the first page (offset=0), replace all content
            if self.current_offset == 0:
                # Check if content actually changed (avoid unnecessary UI updates)
                if not self._has_content_changed(transcriptions):
                    logger.debug("History content unchanged, skipping UI update")
                    # Still update Load More button visibility
                    self.load_more_btn.setVisible(self.has_more_items)
                    return

                # Clear existing
                self._clear_grid()

                # Store data
                self.current_transcriptions = transcriptions

                # Reset widgets list
                self.history_widgets = []
            else:
                # Append mode: add to existing transcriptions
                self.current_transcriptions.extend(transcriptions)

            # Create widgets for new transcriptions
            for trans in transcriptions:
                widget = self._create_history_item_widget(trans)
                widget.show()  # Ensure widget is visible for layout
                self.history_widgets.append(widget)

            # Layout
            self._update_grid_layout()

            # Update Load More button visibility
            self.load_more_btn.setVisible(self.has_more_items)
            if self.has_more_items:
                remaining = total_count - (self.current_offset + len(transcriptions))
                self.load_more_btn.setText(f"Load More... ({remaining} remaining)")
            else:
                self.load_more_btn.setText("Load More...")

            logger.info(f"Loaded {len(transcriptions)} transcriptions (total: {len(self.current_transcriptions)})")

        except Exception as e:
            logger.error(f"Failed to load history: {e}")
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to load history:\n{str(e)}"
            )

    def _load_more(self):
        """Load next page of transcriptions"""
        self.current_offset += self.page_size
        self.load_history(reset=False)  # Don't reset offset
        logger.info(f"Loading more transcriptions (offset={self.current_offset})")

    def search(self, query: str):
        """
        Filter history by text search

        Args:
            query: Search query string
        """
        if not query or not query.strip():
            # Show all items
            for i in range(self.history_list.count()):
                self.history_list.item(i).setHidden(False)
            return

        try:
            # Search in database
            results = self.db.search_transcriptions(query)
            result_ids = {r['id'] for r in results}

            # Filter widgets
            visible_widgets = []
            for widget in self.history_widgets:
                if widget.transcription_id in result_ids:
                    widget.show()
                    visible_widgets.append(widget)
                else:
                    widget.hide()
            
            # Re-layout only visible widgets
            self._reflow_grid(visible_widgets)

            logger.debug(f"Search '{query}' found {len(results)} results")

        except Exception as e:
            logger.error(f"Search failed: {e}")

    def add_transcription_item(self, transcription: dict):
        """
        Add new transcription to top of list
        """
        # Create widget
        widget = self._create_history_item_widget(transcription)
        widget.show() # Ensure widget is visible
        
        # Insert at beginning
        self.history_widgets.insert(0, widget)
        self.current_transcriptions.insert(0, transcription)
        
        # Update layout
        self._update_grid_layout()
        
    def _clear_grid(self):
        """Remove all items from grid"""
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.history_widgets = []

    def eventFilter(self, obj, event):
        """Handle resize events to reflow grid"""
        if obj == self and event.type() == QEvent.Type.Resize:
            self._update_grid_layout()
        return super().eventFilter(obj, event)

    def _update_grid_layout(self):
        """Reflow all widgets"""
        self._reflow_grid(self.history_widgets)

    def _reflow_grid(self, widgets_to_layout):
        """
        Place widgets in grid based on width.
        2 columns if width < 800, 3 columns otherwise.
        """
        # Clear layout (but don't delete widgets!)
        while self.grid_layout.count():
            self.grid_layout.takeAt(0)
            
    def _reflow_grid(self, widgets_to_layout):
        """
        Place widgets in grid.
        Fixed layout: 2 columns.
        """
        # Clear layout (but don't delete widgets!)
        while self.grid_layout.count():
            self.grid_layout.takeAt(0)
            
        cols = 1
        
        for i, widget in enumerate(widgets_to_layout):
            if not widget.isHidden():
                row = i // cols
                col = i % cols
                self.grid_layout.addWidget(widget, row, col)

        # Set column stretch to equal to prevent weird resizing
        for c in range(cols):
            self.grid_layout.setColumnStretch(c, 1)

    def _create_history_item_widget(self, transcription: dict) -> QWidget:
        """
        Create custom widget for single history entry

        Args:
            transcription: Dict with transcription data

        Returns:
            QWidget with formatted content
        """
        widget = QFrame()
        widget.setStyleSheet("""
            QFrame {
                background-color: #2d2d2d;
                border: 1px solid #3d3d3d;
                border-radius: 6px;
                padding: 0px;
            }
            QFrame:hover {
                background-color: #353535;
                border-color: #4d4d4d;
            }
        """)

        # Store ID for search filtering
        widget.transcription_id = transcription['id']

        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(6)

        # Header row: timestamp and copy button
        header_layout = QHBoxLayout()
        header_layout.setSpacing(8)

        timestamp_label = QLabel(transcription['timestamp'])
        timestamp_label.setStyleSheet("color: #888888; font-size: 11px; border: none; background: transparent;")
        header_layout.addWidget(timestamp_label)

        header_layout.addStretch()

        copy_btn = QPushButton("Copy")
        copy_btn.setFixedSize(50, 24)
        copy_btn.clicked.connect(lambda: self._copy_text(transcription['text']))
        copy_btn.setStyleSheet("""
            QPushButton {
                background-color: #3d3d3d;
                border: 1px solid #4d4d4d;
                border-radius: 4px;
                padding: 0px;
                font-size: 11px;
                color: #cccccc;
            }
            QPushButton:hover {
                background-color: #0078d4;
                border-color: #0078d4;
                color: #ffffff;
            }
            QPushButton:pressed {
                background-color: #005a9e;
            }
        """)
        header_layout.addWidget(copy_btn)

        layout.addLayout(header_layout)

        # Text content
        # Text content
        text_label = QLabel(transcription['text'])
        text_label.setWordWrap(True)
        text_label.setStyleSheet("color: #ffffff; font-size: 13px; line-height: 1.4; border: none; background: transparent;")
        text_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        text_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Minimum) # Allow wrap
        layout.addWidget(text_label)

        # Footer: duration and language
        footer_label = QLabel(
            f"Duration: {transcription['duration']:.1f}s | Language: {transcription['language'] or 'auto'}"
        )
        footer_label.setStyleSheet("color: #666666; font-size: 10px; border: none; background: transparent;")
        layout.addWidget(footer_label)

        return widget

    def _copy_text(self, text: str):
        """
        Copy text to clipboard

        Args:
            text: Text to copy
        """
        try:
            clipboard = QApplication.clipboard()
            clipboard.setText(text)
            self.text_copied.emit(text)
            logger.debug(f"Copied {len(text)} characters to clipboard")

            # Show temporary feedback (could enhance with tooltip)
            QMessageBox.information(
                self,
                "Copied",
                "Text copied to clipboard!",
                QMessageBox.StandardButton.Ok
            )

        except Exception as e:
            logger.error(f"Failed to copy text: {e}")

    def export_to_txt(self):
        """Export all visible transcriptions to TXT file"""
        try:
            # Get filename from user
            default_filename = f"whisper-free-history-{datetime.now().strftime('%Y-%m-%d')}.txt"
            filename, _ = QFileDialog.getSaveFileName(
                self,
                "Export to TXT",
                str(Path.home() / default_filename),
                "Text Files (*.txt)"
            )

            if not filename:
                return

            # Export using database method
            self.db.export_to_txt(filename)

            logger.info(f"Exported history to {filename}")
            QMessageBox.information(
                self,
                "Export Successful",
                f"History exported to:\n{filename}"
            )

        except Exception as e:
            logger.error(f"Export to TXT failed: {e}")
            QMessageBox.critical(
                self,
                "Export Failed",
                f"Failed to export to TXT:\n{str(e)}"
            )

    def export_to_json(self):
        """Export all visible transcriptions to JSON file"""
        try:
            # Get filename from user
            default_filename = f"whisper-free-history-{datetime.now().strftime('%Y-%m-%d')}.json"
            filename, _ = QFileDialog.getSaveFileName(
                self,
                "Export to JSON",
                str(Path.home() / default_filename),
                "JSON Files (*.json)"
            )

            if not filename:
                return

            # Export using database method
            self.db.export_to_json(filename)

            logger.info(f"Exported history to {filename}")
            QMessageBox.information(
                self,
                "Export Successful",
                f"History exported to:\n{filename}"
            )

        except Exception as e:
            logger.error(f"Export to JSON failed: {e}")
            QMessageBox.critical(
                self,
                "Export Failed",
                f"Failed to export to JSON:\n{str(e)}"
            )

    def _has_content_changed(self, new_transcriptions: list) -> bool:
        """
        Check if transcription list has actually changed.

        Args:
            new_transcriptions: New transcription list to compare

        Returns:
            True if content changed, False otherwise
        """
        # If lengths differ, content changed
        if len(new_transcriptions) != len(self.current_transcriptions):
            return True

        # If both empty, no change
        if not new_transcriptions:
            return False

        # Compare IDs and timestamps (more efficient than deep comparison)
        for old, new in zip(self.current_transcriptions, new_transcriptions):
            if old.get('id') != new.get('id') or old.get('timestamp') != new.get('timestamp'):
                return True

        # No differences found
        return False

    def _set_filter(self, source_type: str = None):
        """
        Set source type filter and reload history.

        Args:
            source_type: 'microphone', 'file', or None for all
        """
        self.current_filter = source_type

        # Update button states
        self.filter_all_btn.setChecked(source_type is None)
        self.filter_ptt_btn.setChecked(source_type == 'microphone')
        self.filter_file_btn.setChecked(source_type == 'file')

        # Reload with filter applied
        self.load_history()

        logger.debug(f"Filter set to: {source_type or 'all'}")
