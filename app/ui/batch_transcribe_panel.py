"""
BatchTranscribePanel - UI for batch transcribing multiple audio files

Provides interface to select multiple audio files and transcribe them
sequentially with status tracking, progress bars, and retry capabilities.

Author: Whisper-Free Project
License: MIT
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QProgressBar, QFileDialog,
    QHeaderView, QAbstractItemView, QMessageBox, QApplication
)
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QColor, QIcon
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class FileStatus:
    """File transcription status constants with icons"""
    PENDING = "⏸️ Pending"
    RUNNING = "▶️ Processing"
    PAUSED = "⏸️ Paused"
    COMPLETED = "✅ Completed"
    FAILED = "❌ Failed"


class BatchTranscribePanel(QWidget):
    """
    Panel for batch transcribing multiple audio files.

    Features:
    - Multiple file selection
    - Per-file status tracking with icons
    - Individual progress bars
    - Overall batch progress
    - Retry failed files
    - Cancel running files
    - Integration with TranscriptionQueueManager
    """

    # Signals
    batch_started = Signal(list)  # file_paths
    batch_paused = Signal()
    batch_resumed = Signal()
    batch_cancelled = Signal()

    def __init__(self, queue_manager, config_manager, db_manager, parent=None):
        """
        Initialize batch transcribe panel.

        Args:
            queue_manager: TranscriptionQueueManager instance
            config_manager: ConfigManager instance
            db_manager: DatabaseManager instance
            parent: Parent widget
        """
        super().__init__(parent)
        self.queue = queue_manager
        self.config = config_manager
        self.db = db_manager

        # State
        self.job_ids = {}  # file_path -> job_id mapping
        self.file_paths = {}  # job_id -> file_path mapping
        self.error_messages = {}  # file_path -> error_message mapping

        self._setup_ui()
        self._connect_signals()

        logger.info("BatchTranscribePanel initialized")

    def _setup_ui(self):
        """Create UI layout"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Header
        header_layout = QHBoxLayout()
        header = QLabel("Batch File Transcription")
        header.setStyleSheet("font-size: 24px; font-weight: bold; color: #ffffff;")
        header_layout.addWidget(header)
        header_layout.addStretch()

        # Help text
        help_text = QLabel("Add multiple files and transcribe them sequentially")
        help_text.setStyleSheet("color: #888888; font-size: 12px;")
        header_layout.addWidget(help_text)

        layout.addLayout(header_layout)

        # File list table
        self.file_table = QTableWidget()
        self.file_table.setColumnCount(5)
        self.file_table.setHorizontalHeaderLabels([
            "File Name", "Status", "Progress", "Duration", "Actions"
        ])

        # Table styling
        self.file_table.setStyleSheet("""
            QTableWidget {
                background-color: #2d2d2d;
                border: 1px solid #3d3d3d;
                border-radius: 6px;
                gridline-color: #3d3d3d;
            }
            QTableWidget::item {
                padding: 8px;
                color: #ffffff;
            }
            QTableWidget::item:selected {
                background-color: #0078d4;
            }
            QHeaderView::section {
                background-color: #3d3d3d;
                color: #ffffff;
                padding: 8px;
                border: none;
                font-weight: bold;
            }
        """)

        # Table settings
        self.file_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.file_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.file_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.file_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.file_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Fixed)
        self.file_table.setColumnWidth(2, 150)  # Progress bar column
        self.file_table.setColumnWidth(4, 100)  # Actions column (enough for 2-3 icon buttons)

        self.file_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.file_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.file_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.file_table.setAlternatingRowColors(True)

        layout.addWidget(self.file_table)

        # Control buttons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(8)

        self.add_files_btn = self._create_button("➕ Add Files", "#0078d4")
        self.add_files_btn.clicked.connect(self._on_add_files)
        button_layout.addWidget(self.add_files_btn)

        self.remove_files_btn = self._create_button("➖ Remove Selected", "#d41e00")
        self.remove_files_btn.clicked.connect(self._on_remove_files)
        button_layout.addWidget(self.remove_files_btn)

        self.start_batch_btn = self._create_button("▶️ Start Batch", "#107c10")
        self.start_batch_btn.clicked.connect(self._on_start_batch)
        button_layout.addWidget(self.start_batch_btn)

        self.clear_completed_btn = self._create_button("🗑️ Clear Completed", "#666666")
        self.clear_completed_btn.clicked.connect(self._on_clear_completed)
        button_layout.addWidget(self.clear_completed_btn)

        button_layout.addStretch()
        layout.addLayout(button_layout)

        # Overall progress
        progress_layout = QHBoxLayout()
        progress_layout.setSpacing(12)

        progress_label = QLabel("Overall Progress:")
        progress_label.setStyleSheet("color: #ffffff; font-weight: bold;")
        progress_layout.addWidget(progress_label)

        self.overall_progress = QProgressBar()
        self.overall_progress.setRange(0, 100)
        self.overall_progress.setValue(0)
        self.overall_progress.setTextVisible(True)
        self.overall_progress.setStyleSheet("""
            QProgressBar {
                border: 1px solid #3d3d3d;
                border-radius: 4px;
                background-color: #2d2d2d;
                text-align: center;
                color: #ffffff;
                height: 24px;
            }
            QProgressBar::chunk {
                background-color: #0078d4;
                border-radius: 3px;
            }
        """)
        progress_layout.addWidget(self.overall_progress, 1)

        self.progress_label = QLabel("0 / 0 files")
        self.progress_label.setStyleSheet("color: #888888; font-size: 12px;")
        progress_layout.addWidget(self.progress_label)

        layout.addLayout(progress_layout)

    def _create_button(self, text: str, color: str) -> QPushButton:
        """Create styled button"""
        btn = QPushButton(text)
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {color};
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-size: 13px;
                font-weight: bold;
                color: #ffffff;
            }}
            QPushButton:hover {{
                background-color: {self._lighten_color(color)};
            }}
            QPushButton:pressed {{
                background-color: {self._darken_color(color)};
            }}
            QPushButton:disabled {{
                background-color: #3d3d3d;
                color: #666666;
            }}
        """)
        return btn

    def _lighten_color(self, hex_color: str) -> str:
        """Lighten a hex color by 20%"""
        color = QColor(hex_color)
        h, s, l, a = color.getHsl()
        return QColor.fromHsl(h, s, min(255, int(l * 1.2)), a).name()

    def _darken_color(self, hex_color: str) -> str:
        """Darken a hex color by 20%"""
        color = QColor(hex_color)
        h, s, l, a = color.getHsl()
        return QColor.fromHsl(h, s, int(l * 0.8), a).name()

    def _connect_signals(self):
        """Connect to queue manager signals"""
        self.queue.job_started.connect(self._on_job_started)
        self.queue.job_progress.connect(self._on_job_progress)
        self.queue.job_paused.connect(self._on_job_paused)
        self.queue.job_resumed.connect(self._on_job_resumed)
        self.queue.job_completed.connect(self._on_job_completed)
        self.queue.job_failed.connect(self._on_job_failed)

    @Slot()
    def _on_add_files(self):
        """Open file dialog to add multiple files"""
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Audio Files",
            self.config.get('file_transcribe.last_directory', ''),
            "Audio Files (*.mp3 *.wav *.m4a *.flac *.ogg *.opus *.webm *.mp4 *.avi *.mkv)"
        )

        if not file_paths:
            return

        # Update last directory
        self.config.set('file_transcribe.last_directory',
                        str(Path(file_paths[0]).parent))

        # Add files to table
        for path in file_paths:
            if not self._is_file_in_table(path):
                self._add_file_to_table(path)

        logger.info(f"Added {len(file_paths)} files to batch")

    def _is_file_in_table(self, file_path: str) -> bool:
        """Check if file is already in table"""
        for row in range(self.file_table.rowCount()):
            name_item = self.file_table.item(row, 0)
            if name_item and name_item.data(Qt.UserRole) == file_path:
                return True
        return False

    def _add_file_to_table(self, file_path: str):
        """Add a file row to the table"""
        row = self.file_table.rowCount()
        self.file_table.insertRow(row)

        # File name
        name_item = QTableWidgetItem(Path(file_path).name)
        name_item.setData(Qt.UserRole, file_path)  # Store full path
        name_item.setToolTip(file_path)
        self.file_table.setItem(row, 0, name_item)

        # Status
        status_item = QTableWidgetItem(FileStatus.PENDING)
        status_item.setForeground(QColor("#888888"))
        self.file_table.setItem(row, 1, status_item)

        # Progress bar
        progress_bar = QProgressBar()
        progress_bar.setRange(0, 100)
        progress_bar.setValue(0)
        progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #3d3d3d;
                border-radius: 3px;
                background-color: #1d1d1d;
                text-align: center;
                color: #ffffff;
                height: 20px;
            }
            QProgressBar::chunk {
                background-color: #0078d4;
                border-radius: 2px;
            }
        """)
        self.file_table.setCellWidget(row, 2, progress_bar)

        # Duration (initially unknown)
        duration_item = QTableWidgetItem("--:--")
        duration_item.setTextAlignment(Qt.AlignCenter)
        self.file_table.setItem(row, 3, duration_item)

        # Action buttons
        action_widget = QWidget()
        action_layout = QHBoxLayout(action_widget)
        action_layout.setContentsMargins(4, 4, 4, 4)
        action_layout.setSpacing(4)

        retry_btn = QPushButton("🔄")
        retry_btn.setToolTip("Retry transcription")
        retry_btn.setFixedSize(28, 28)
        retry_btn.setEnabled(False)
        retry_btn.clicked.connect(lambda: self._retry_file(file_path))
        retry_btn.setStyleSheet("""
            QPushButton {
                background-color: #3d3d3d;
                border: none;
                border-radius: 4px;
                font-size: 14px;
            }
            QPushButton:hover:enabled {
                background-color: #4d4d4d;
            }
            QPushButton:disabled {
                color: #666666;
            }
        """)
        action_layout.addWidget(retry_btn)

        cancel_btn = QPushButton("✖️")
        cancel_btn.setToolTip("Cancel transcription")
        cancel_btn.setFixedSize(28, 28)
        cancel_btn.setEnabled(False)
        cancel_btn.clicked.connect(lambda: self._cancel_file(file_path))
        cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #3d3d3d;
                border: none;
                border-radius: 4px;
                font-size: 14px;
            }
            QPushButton:hover:enabled {
                background-color: #d41e00;
            }
            QPushButton:disabled {
                color: #666666;
            }
        """)
        action_layout.addWidget(cancel_btn)

        details_btn = QPushButton("ℹ️")
        details_btn.setToolTip("View error details")
        details_btn.setFixedSize(28, 28)
        details_btn.setEnabled(False)
        details_btn.clicked.connect(lambda: self._show_error_details(file_path))
        details_btn.setStyleSheet("""
            QPushButton {
                background-color: #3d3d3d;
                border: none;
                border-radius: 4px;
                font-size: 14px;
            }
            QPushButton:hover:enabled {
                background-color: #4d4d4d;
            }
            QPushButton:disabled {
                color: #666666;
            }
        """)
        action_layout.addWidget(details_btn)

        self.file_table.setCellWidget(row, 4, action_widget)

    @Slot()
    def _on_remove_files(self):
        """Remove selected files from table"""
        selected_rows = set(index.row() for index in self.file_table.selectedIndexes())

        # Remove rows in reverse order to avoid index shifting
        for row in sorted(selected_rows, reverse=True):
            self.file_table.removeRow(row)

        logger.info(f"Removed {len(selected_rows)} files from batch")
        self._update_overall_progress()

    @Slot()
    def _on_start_batch(self):
        """Submit all pending files as batch jobs"""
        file_paths = []

        for row in range(self.file_table.rowCount()):
            status_item = self.file_table.item(row, 1)
            if status_item and status_item.text() == FileStatus.PENDING:
                name_item = self.file_table.item(row, 0)
                file_paths.append(name_item.data(Qt.UserRole))

        if not file_paths:
            QMessageBox.information(
                self,
                "No Files",
                "No pending files to transcribe.\n\n"
                "Add files using the 'Add Files' button."
            )
            return

        # Get transcription settings
        language = self.config.get('whisper.language')
        settings = {
            'fp16': self.config.get('whisper.fp16', True),
            'beam_size': self.config.get('whisper.beam_size', 1),
            'temperature': self.config.get('whisper.temperature', 0.0)
        }

        # Submit batch to queue manager
        job_ids = self.queue.submit_batch_jobs(file_paths, language, settings)

        # Store job IDs
        for path, job_id in zip(file_paths, job_ids):
            self.job_ids[path] = job_id
            self.file_paths[job_id] = path

        # Update UI
        self.start_batch_btn.setEnabled(False)

        self.batch_started.emit(file_paths)
        logger.info(f"Started batch transcription of {len(file_paths)} files")

    @Slot()
    def _on_clear_completed(self):
        """Remove all completed and failed files from table"""
        rows_to_remove = []

        for row in range(self.file_table.rowCount()):
            status_item = self.file_table.item(row, 1)
            if status_item:
                status = status_item.text()
                if status in [FileStatus.COMPLETED, FileStatus.FAILED]:
                    rows_to_remove.append(row)

        # Remove rows in reverse order
        for row in sorted(rows_to_remove, reverse=True):
            self.file_table.removeRow(row)

        logger.info(f"Cleared {len(rows_to_remove)} completed/failed files")
        self._update_overall_progress()

    @Slot(str)
    def _on_job_started(self, job_id: str):
        """Update UI when a job starts"""
        file_path = self.file_paths.get(job_id)
        if not file_path:
            return

        row = self._get_row_by_file_path(file_path)
        if row is None:
            return

        # Update status
        status_item = self.file_table.item(row, 1)
        status_item.setText(FileStatus.RUNNING)
        status_item.setForeground(QColor("#2196F3"))  # Blue

        # Enable cancel button
        action_widget = self.file_table.cellWidget(row, 4)
        if action_widget:
            buttons = action_widget.findChildren(QPushButton)
            if len(buttons) >= 2:
                buttons[1].setEnabled(True)  # Cancel button

        logger.debug(f"Job {job_id} started for {Path(file_path).name}")

    @Slot(str, int)
    def _on_job_progress(self, job_id: str, percentage: int):
        """Update progress bar when job progresses"""
        file_path = self.file_paths.get(job_id)
        if not file_path:
            return

        row = self._get_row_by_file_path(file_path)
        if row is None:
            return

        # Update progress bar
        progress_bar = self.file_table.cellWidget(row, 2)
        if isinstance(progress_bar, QProgressBar):
            progress_bar.setValue(percentage)

        # Update overall progress
        self._update_overall_progress()

    @Slot(str, int)
    def _on_job_paused(self, job_id: str, chunk_index: int):
        """Update UI when job is paused"""
        file_path = self.file_paths.get(job_id)
        if not file_path:
            return

        row = self._get_row_by_file_path(file_path)
        if row is None:
            return

        # Update status
        status_item = self.file_table.item(row, 1)
        status_item.setText(FileStatus.PAUSED)
        status_item.setForeground(QColor("#FFA500"))  # Orange

        logger.debug(f"Job {job_id} paused at chunk {chunk_index}")

    @Slot(str, int)
    def _on_job_resumed(self, job_id: str, chunk_index: int):
        """Update UI when job is resumed"""
        file_path = self.file_paths.get(job_id)
        if not file_path:
            return

        row = self._get_row_by_file_path(file_path)
        if row is None:
            return

        # Update status back to RUNNING
        status_item = self.file_table.item(row, 1)
        status_item.setText(FileStatus.RUNNING)
        status_item.setForeground(QColor("#2196F3"))  # Blue

        logger.debug(f"Job {job_id} resumed from chunk {chunk_index}")

    @Slot(str, str, dict)
    def _on_job_completed(self, job_id: str, result_text: str, result_data: dict):
        """Update UI when job completes successfully"""
        file_path = self.file_paths.get(job_id)
        if not file_path:
            return

        row = self._get_row_by_file_path(file_path)
        if row is None:
            return

        # Update status
        status_item = self.file_table.item(row, 1)
        status_item.setText(FileStatus.COMPLETED)
        status_item.setForeground(QColor("#4CAF50"))  # Green

        # Set progress to 100%
        progress_bar = self.file_table.cellWidget(row, 2)
        if isinstance(progress_bar, QProgressBar):
            progress_bar.setValue(100)

        # Update duration if available
        segments = result_data.get('segments', [])
        if segments:
            duration_seconds = segments[-1].get('end', 0)
            minutes = int(duration_seconds // 60)
            seconds = int(duration_seconds % 60)
            duration_item = self.file_table.item(row, 3)
            duration_item.setText(f"{minutes:02d}:{seconds:02d}")

        # Disable all action buttons
        action_widget = self.file_table.cellWidget(row, 4)
        if action_widget:
            for btn in action_widget.findChildren(QPushButton):
                btn.setEnabled(False)

        # Update overall progress
        self._update_overall_progress()
        self._check_batch_completion()

        logger.info(f"Job {job_id} completed: {Path(file_path).name} ({len(result_text)} chars)")

    @Slot(str, str)
    def _on_job_failed(self, job_id: str, error_message: str):
        """Update UI when job fails"""
        file_path = self.file_paths.get(job_id)
        if not file_path:
            return

        row = self._get_row_by_file_path(file_path)
        if row is None:
            return

        # Store error message
        self.error_messages[file_path] = error_message

        # Update status
        status_item = self.file_table.item(row, 1)
        status_item.setText(FileStatus.FAILED)
        status_item.setForeground(QColor("#F44336"))  # Red
        status_item.setToolTip(f"Error: {error_message}")

        # Enable retry and details buttons, disable cancel
        action_widget = self.file_table.cellWidget(row, 4)
        if action_widget:
            buttons = action_widget.findChildren(QPushButton)
            if len(buttons) >= 3:
                buttons[0].setEnabled(True)   # Retry
                buttons[1].setEnabled(False)  # Cancel
                buttons[2].setEnabled(True)   # Details

        # Update overall progress
        self._update_overall_progress()

        logger.error(f"Job {job_id} failed: {Path(file_path).name} - {error_message}")

    def _update_overall_progress(self):
        """Recalculate overall batch progress"""
        total_files = self.file_table.rowCount()
        if total_files == 0:
            self.overall_progress.setValue(0)
            self.progress_label.setText("0 / 0 files")
            return

        completed = 0
        total_progress = 0

        for row in range(total_files):
            status_item = self.file_table.item(row, 1)
            if not status_item:
                continue

            status = status_item.text()

            if status == FileStatus.COMPLETED:
                completed += 1
                total_progress += 100
            elif status == FileStatus.RUNNING:
                progress_bar = self.file_table.cellWidget(row, 2)
                if isinstance(progress_bar, QProgressBar):
                    total_progress += progress_bar.value()

        overall_percentage = int(total_progress / total_files) if total_files > 0 else 0
        self.overall_progress.setValue(overall_percentage)
        self.progress_label.setText(f"{completed} / {total_files} files")

    def _check_batch_completion(self):
        """Check if all jobs are done, show summary if batch is complete"""
        all_done = True
        completed_count = 0
        failed_count = 0

        for row in range(self.file_table.rowCount()):
            status_item = self.file_table.item(row, 1)
            if not status_item:
                continue

            status = status_item.text()
            if status in [FileStatus.PENDING, FileStatus.RUNNING, FileStatus.PAUSED]:
                all_done = False
                break
            elif status == FileStatus.COMPLETED:
                completed_count += 1
            elif status == FileStatus.FAILED:
                failed_count += 1

        if all_done and self.file_table.rowCount() > 0:
            self.start_batch_btn.setEnabled(True)
            logger.info("Batch transcription completed")

            # Show completion summary
            total_files = self.file_table.rowCount()
            if failed_count == 0:
                QMessageBox.information(
                    self,
                    "Batch Complete",
                    f"All files transcribed successfully!\n\n"
                    f"Completed: {completed_count} / {total_files} files"
                )
            else:
                result = QMessageBox.warning(
                    self,
                    "Batch Complete with Errors",
                    f"Batch transcription finished with some errors.\n\n"
                    f"✅ Completed: {completed_count}\n"
                    f"❌ Failed: {failed_count}\n"
                    f"Total: {total_files}\n\n"
                    f"Click on the ℹ️ button next to failed files to view error details.",
                    QMessageBox.Ok | QMessageBox.Retry
                )

                # If user clicked Retry, retry all failed files
                if result == QMessageBox.Retry:
                    for row in range(self.file_table.rowCount()):
                        status_item = self.file_table.item(row, 1)
                        if status_item and status_item.text() == FileStatus.FAILED:
                            name_item = self.file_table.item(row, 0)
                            file_path = name_item.data(Qt.UserRole)
                            self._retry_file(file_path)

    def _get_row_by_file_path(self, file_path: str) -> int:
        """Find table row by file path"""
        for row in range(self.file_table.rowCount()):
            name_item = self.file_table.item(row, 0)
            if name_item and name_item.data(Qt.UserRole) == file_path:
                return row
        return None

    def _retry_file(self, file_path: str):
        """Retry a failed file"""
        job_id = self.job_ids.get(file_path)
        if job_id:
            self.queue.retry_job(job_id)

            # Reset UI
            row = self._get_row_by_file_path(file_path)
            if row is not None:
                status_item = self.file_table.item(row, 1)
                status_item.setText(FileStatus.PENDING)
                status_item.setForeground(QColor("#888888"))
                status_item.setToolTip("")

                progress_bar = self.file_table.cellWidget(row, 2)
                if isinstance(progress_bar, QProgressBar):
                    progress_bar.setValue(0)

                # Disable retry, keep cancel disabled
                action_widget = self.file_table.cellWidget(row, 4)
                if action_widget:
                    buttons = action_widget.findChildren(QPushButton)
                    if len(buttons) >= 2:
                        buttons[0].setEnabled(False)  # Retry
                        buttons[1].setEnabled(False)  # Cancel

            logger.info(f"Retrying file: {Path(file_path).name}")

    def _cancel_file(self, file_path: str):
        """Cancel a running file"""
        job_id = self.job_ids.get(file_path)
        if job_id:
            self.queue.cancel_job(job_id)
            logger.info(f"Cancelled file: {Path(file_path).name}")

    def _show_error_details(self, file_path: str):
        """Show detailed error dialog for failed file"""
        error_message = self.error_messages.get(file_path, "No error details available")

        # Create detailed error message
        filename = Path(file_path).name
        details = f"File: {filename}\n\n"
        details += f"Full Path:\n{file_path}\n\n"
        details += f"Error Details:\n{error_message}\n\n"
        details += "Troubleshooting:\n"

        # Add contextual suggestions based on error message
        error_lower = error_message.lower()
        if "file not found" in error_lower or "no such file" in error_lower:
            details += "• File may have been moved or deleted\n"
            details += "• Check that the file still exists at the specified location\n"
        elif "permission" in error_lower or "access" in error_lower:
            details += "• Check file permissions\n"
            details += "• Make sure the file is not locked by another program\n"
        elif "format" in error_lower or "codec" in error_lower or "unsupported" in error_lower:
            details += "• File format may not be supported\n"
            details += "• Try converting to .mp3 or .wav format\n"
        elif "corrupt" in error_lower or "damaged" in error_lower:
            details += "• File may be corrupted or incomplete\n"
            details += "• Try re-downloading or re-recording the audio\n"
        elif "memory" in error_lower or "vram" in error_lower:
            details += "• Insufficient GPU memory\n"
            details += "• Try using a smaller Whisper model in Settings\n"
            details += "• Close other GPU-intensive applications\n"
        else:
            details += "• Check the log file for more details\n"
            details += "• Try transcribing the file again\n"
            details += "• Contact support if the issue persists\n"

        # Show detailed error dialog
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Transcription Error Details")
        msg_box.setIcon(QMessageBox.Critical)
        msg_box.setText(f"Failed to transcribe: {filename}")
        msg_box.setDetailedText(details)
        msg_box.setStandardButtons(QMessageBox.Ok | QMessageBox.Retry)
        msg_box.setDefaultButton(QMessageBox.Retry)

        result = msg_box.exec()
        if result == QMessageBox.Retry:
            self._retry_file(file_path)
