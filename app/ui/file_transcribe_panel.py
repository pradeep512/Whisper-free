"""
FileTranscribePanel - UI for transcribing audio files

Provides interface to select audio files, transcribe them using Whisper,
and save transcriptions as .txt files. Shows progress and results.

Author: Whisper-Free Project
License: MIT
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QPushButton, QTextEdit, QProgressBar, QFileDialog,
    QScrollArea, QApplication, QMessageBox, QCheckBox, QGridLayout
)
from PySide6.QtCore import Qt, Signal, QThread, QUrl
from PySide6.QtGui import QDesktopServices
from pathlib import Path
import logging

from app.core.audio_file_loader import AudioFileLoader, AudioLoadError
from app.core.transcription_queue_manager import JobPriority
from app.core.transcription_formats import TranscriptionFormatter
from datetime import datetime

logger = logging.getLogger(__name__)


class FileTranscribePanel(QWidget):
    """
    Panel for transcribing audio files.

    Features:
    - File selection with format filter
    - Progress display during transcription
    - Result text display with copy/open/clear buttons
    - Database integration
    - Config-based settings
    """

    # Signals
    file_transcribed = Signal(dict)  # Emitted when transcription completes

    def __init__(self, config_manager, whisper_engine, db_manager, queue_manager, parent=None):
        """
        Initialize file transcribe panel.

        Args:
            config_manager: ConfigManager instance
            whisper_engine: WhisperEngine instance
            db_manager: DatabaseManager instance
            queue_manager: TranscriptionQueueManager instance
            parent: Parent widget
        """
        super().__init__(parent)
        self.config = config_manager
        self.whisper_engine = whisper_engine
        self.db_manager = db_manager
        self.queue_manager = queue_manager

        # State
        self.selected_file_path = None
        self.current_job_id = None
        self.last_output_path = None
        self.last_transcription_text = ""

        self._setup_ui()

        logger.info("FileTranscribePanel initialized")

    def _setup_ui(self):
        """Create UI layout"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Header
        header = QLabel("File Transcribe")
        header.setStyleSheet("font-size: 24px; font-weight: bold; color: #ffffff;")
        layout.addWidget(header)

        # Scrollable area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setStyleSheet(self._scroll_style())

        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setSpacing(16)
        scroll_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Add sections
        scroll_layout.addWidget(self._create_file_selection_group())
        scroll_layout.addWidget(self._create_settings_display_group())
        scroll_layout.addWidget(self._create_output_format_group())
        scroll_layout.addWidget(self._create_transcription_group())
        scroll_layout.addWidget(self._create_results_group())

        scroll.setWidget(scroll_content)
        layout.addWidget(scroll, 1)

    def _create_file_selection_group(self) -> QGroupBox:
        """Create file selection section"""
        group = QGroupBox("Select Audio File")
        group.setStyleSheet(self._group_style())

        layout = QVBoxLayout(group)
        layout.setContentsMargins(16, 24, 16, 16)
        layout.setSpacing(12)

        # File info labels
        self.file_label = QLabel("No file selected")
        self.file_label.setStyleSheet("color: #888888; font-style: italic;")
        self.file_label.setWordWrap(True)
        layout.addWidget(self.file_label)

        self.duration_label = QLabel("")
        self.duration_label.setStyleSheet("color: #cccccc;")
        layout.addWidget(self.duration_label)

        # Browse button
        self.browse_button = QPushButton("Browse...")
        self.browse_button.clicked.connect(self._on_browse_clicked)
        self.browse_button.setStyleSheet(self._button_style())
        layout.addWidget(self.browse_button)

        return group

    def _create_settings_display_group(self) -> QGroupBox:
        """Create settings display section (read-only)"""
        group = QGroupBox("Transcription Settings")
        group.setStyleSheet(self._group_style())

        layout = QVBoxLayout(group)
        layout.setContentsMargins(16, 24, 16, 16)
        layout.setSpacing(8)

        # Model
        model_name = self.config.get('whisper.model', 'small')
        model_label = QLabel(f"Model: {model_name}")
        model_label.setStyleSheet("color: #cccccc;")
        layout.addWidget(model_label)

        # Language
        language = self.config.get('whisper.language')
        lang_text = language if language else "Auto-detect"
        lang_label = QLabel(f"Language: {lang_text}")
        lang_label.setStyleSheet("color: #cccccc;")
        layout.addWidget(lang_label)

        # Device
        device = self.config.get('whisper.device', 'cuda')
        device_label = QLabel(f"Device: {device.upper()}")
        device_label.setStyleSheet("color: #cccccc;")
        layout.addWidget(device_label)

        # Info text
        info = QLabel("Settings are configured in the Settings panel")
        info.setStyleSheet("color: #666666; font-size: 12px; font-style: italic; margin-top: 8px;")
        info.setWordWrap(True)
        layout.addWidget(info)

        return group

    def _create_output_format_group(self) -> QGroupBox:
        """Create output format selection section"""
        group = QGroupBox("Output Formats")
        group.setStyleSheet(self._group_style())

        layout = QVBoxLayout(group)
        layout.setContentsMargins(16, 24, 16, 16)
        layout.setSpacing(12)

        # Info label
        info_label = QLabel("Select which file formats to create:")
        info_label.setStyleSheet("color: #cccccc;")
        layout.addWidget(info_label)

        # Format checkboxes in a grid
        checkbox_layout = QGridLayout()
        checkbox_layout.setSpacing(8)

        # Create checkboxes for each format
        self.format_checkboxes = {}

        formats = [
            ('txt', 'Plain Text (.txt)', 'Basic text transcription'),
            ('srt', 'SRT Subtitles (.srt)', 'For video editing software'),
            ('vtt', 'WebVTT (.vtt)', 'For web video players'),
            ('json', 'JSON (.json)', 'Full data with timestamps'),
            ('tsv', 'TSV (.tsv)', 'Tab-separated timestamps'),
        ]

        for i, (format_key, label, tooltip) in enumerate(formats):
            checkbox = QCheckBox(label)
            checkbox.setToolTip(tooltip)
            checkbox.setStyleSheet("color: #ffffff;")

            # Load initial state from config
            enabled = self.config.get(f'file_transcribe.output_formats.{format_key}', format_key == 'txt')
            checkbox.setChecked(enabled)

            # Connect signal to save config
            checkbox.stateChanged.connect(
                lambda state, key=format_key: self._on_format_checkbox_changed(key, state)
            )

            self.format_checkboxes[format_key] = checkbox

            # Add to grid (2 columns)
            row = i // 2
            col = i % 2
            checkbox_layout.addWidget(checkbox, row, col)

        layout.addLayout(checkbox_layout)

        # Note about text display
        note = QLabel("Note: Only .txt content will be displayed below. Other formats will be created as files.")
        note.setStyleSheet("color: #666666; font-size: 11px; font-style: italic; margin-top: 8px;")
        note.setWordWrap(True)
        layout.addWidget(note)

        return group

    def _on_format_checkbox_changed(self, format_key: str, state: int):
        """Handle format checkbox change"""
        enabled = state == Qt.CheckState.Checked.value

        # Update config
        self.config.set(f'file_transcribe.output_formats.{format_key}', enabled)
        self.config.save()

        logger.debug(f"Output format {format_key} set to {enabled}")

        # Ensure at least one format is enabled
        any_enabled = any(cb.isChecked() for cb in self.format_checkboxes.values())
        if not any_enabled:
            # Re-enable txt as default
            self.format_checkboxes['txt'].setChecked(True)
            QMessageBox.information(
                self,
                "Format Required",
                "At least one output format must be enabled. TXT format has been re-enabled."
            )

    def _create_transcription_group(self) -> QGroupBox:
        """Create transcription control section"""
        group = QGroupBox("Transcribe")
        group.setStyleSheet(self._group_style())

        layout = QVBoxLayout(group)
        layout.setContentsMargins(16, 24, 16, 16)
        layout.setSpacing(12)

        # Transcribe button
        self.transcribe_button = QPushButton("Transcribe File")
        self.transcribe_button.clicked.connect(self._on_transcribe_clicked)
        self.transcribe_button.setEnabled(False)  # Disabled until file selected
        self.transcribe_button.setStyleSheet(self._primary_button_style())
        layout.addWidget(self.transcribe_button)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setStyleSheet(self._progress_bar_style())
        layout.addWidget(self.progress_bar)

        # Status label
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #888888; font-style: italic;")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        return group

    def _create_results_group(self) -> QGroupBox:
        """Create results display section"""
        group = QGroupBox("Transcription Result")
        group.setStyleSheet(self._group_style())

        layout = QVBoxLayout(group)
        layout.setContentsMargins(16, 24, 16, 16)
        layout.setSpacing(12)

        # Result text area
        self.result_text_edit = QTextEdit()
        self.result_text_edit.setPlaceholderText("Transcription will appear here...")
        self.result_text_edit.setReadOnly(True)
        self.result_text_edit.setMinimumHeight(150)
        self.result_text_edit.setStyleSheet(self._text_edit_style())
        layout.addWidget(self.result_text_edit)

        # Output path label
        self.output_path_label = QLabel("")
        self.output_path_label.setStyleSheet("color: #888888; font-size: 12px; font-style: italic;")
        self.output_path_label.setWordWrap(True)
        layout.addWidget(self.output_path_label)

        # Action buttons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(8)

        self.copy_button = QPushButton("Copy to Clipboard")
        self.copy_button.clicked.connect(self._on_copy_clicked)
        self.copy_button.setEnabled(False)
        self.copy_button.setStyleSheet(self._button_style())
        button_layout.addWidget(self.copy_button)

        self.open_button = QPushButton("Open Output File")
        self.open_button.clicked.connect(self._on_open_file_clicked)
        self.open_button.setEnabled(False)
        self.open_button.setStyleSheet(self._button_style())
        button_layout.addWidget(self.open_button)

        self.clear_button = QPushButton("Clear")
        self.clear_button.clicked.connect(self._on_clear_clicked)
        self.clear_button.setStyleSheet(self._button_style())
        button_layout.addWidget(self.clear_button)

        button_layout.addStretch()
        layout.addLayout(button_layout)

        return group

    def _on_browse_clicked(self):
        """Handle browse button click"""
        logger.info("Browse button clicked")

        # Get last directory from config
        last_dir = self.config.get('file_transcribe.last_directory', str(Path.home()))

        # Create filter string from supported formats
        formats = AudioFileLoader.SUPPORTED_FORMATS
        format_patterns = " ".join([f"*{fmt}" for fmt in formats])
        filter_str = f"Audio Files ({format_patterns});;All Files (*.*)"

        # Open file dialog
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Audio File",
            last_dir,
            filter_str
        )

        if file_path:
            logger.info(f"File selected: {file_path}")
            self._on_file_selected(file_path)

    def _on_file_selected(self, file_path: str):
        """Handle file selection"""
        try:
            # Validate file
            is_valid, error_msg = AudioFileLoader.validate_file(file_path)
            if not is_valid:
                logger.error(f"Invalid file: {error_msg}")
                QMessageBox.warning(
                    self,
                    "Invalid File",
                    f"Cannot use this file:\n\n{error_msg}"
                )
                return

            # Get duration
            try:
                duration = AudioFileLoader.get_duration(file_path)
                duration_text = f"Duration: {self._format_duration(duration)}"
                self.duration_label.setText(duration_text)
            except AudioLoadError as e:
                logger.warning(f"Could not get duration: {e}")
                self.duration_label.setText("Duration: Unknown")

            # Update UI
            self.selected_file_path = file_path
            self.file_label.setText(f"Selected: {Path(file_path).name}")
            self.file_label.setStyleSheet("color: #00ff00;")
            self.transcribe_button.setEnabled(True)

            # Save last directory
            self.config.set('file_transcribe.last_directory', str(Path(file_path).parent))
            self.config.save()

            logger.info(f"File ready for transcription: {file_path}")

        except Exception as e:
            logger.error(f"Error handling file selection: {e}")
            QMessageBox.critical(
                self,
                "Error",
                f"Error selecting file:\n\n{str(e)}"
            )

    def _on_transcribe_clicked(self):
        """Handle transcribe button click"""
        if not self.selected_file_path:
            return

        logger.info(f"Starting transcription via queue manager: {self.selected_file_path}")

        # Disable UI during transcription
        self._set_ui_enabled(False)

        # Reset progress
        self.progress_bar.setValue(0)
        self.status_label.setText("Queued...")

        # Get transcription settings from config
        language = self.config.get('whisper.language')  # None for auto-detect
        settings = {
            'beam_size': self.config.get('whisper.beam_size', 1),
            'temperature': self.config.get('whisper.temperature', 0.0),
            'best_of': self.config.get('whisper.best_of', 1),
        }

        # Submit to queue manager (NORMAL priority for file transcription)
        self.current_job_id = self.queue_manager.submit_file_job(
            file_path=self.selected_file_path,
            language=language,
            settings=settings,
            priority=JobPriority.NORMAL,
            on_progress=self._on_queue_progress,
            on_complete=self._on_queue_complete
        )

        logger.info(f"Submitted file job {self.current_job_id} to queue")

    def _on_queue_progress(self, progress: int):
        """Handle progress update from queue manager"""
        self.progress_bar.setValue(progress)
        if progress == 0:
            self.status_label.setText("Loading audio...")
        elif progress < 100:
            self.status_label.setText(f"Transcribing... {progress}%")
        else:
            self.status_label.setText("Finalizing...")
        logger.debug(f"Progress: {progress}%")

    def _on_queue_complete(self, result_text: str, result_data: dict):
        """Handle completion from queue manager"""
        logger.info("File transcription complete via queue manager")

        try:
            # Extract result data from Whisper result
            language = result_data.get('language', 'unknown')
            duration = 0.0
            if 'segments' in result_data and result_data['segments']:
                last_segment = result_data['segments'][-1]
                duration = last_segment.get('end', 0.0)

            # Save output files
            output_paths = self._save_output_files(result_text, result_data)
            output_path = output_paths[0] if output_paths else ""

            # Display result
            self.result_text_edit.setPlainText(result_text)
            self.last_transcription_text = result_text
            self.last_output_path = output_path

            # Show created files
            if len(output_paths) == 1:
                self.output_path_label.setText(f"Saved to: {output_paths[0]}")
            else:
                files_list = "\n  • ".join([Path(p).name for p in output_paths])
                self.output_path_label.setText(
                    f"Created {len(output_paths)} files:\n  • {files_list}"
                )

            # Enable result buttons
            self.copy_button.setEnabled(True)
            self.open_button.setEnabled(True)

            # Update status
            self.status_label.setText(f"Complete! ({len(result_text)} characters, {language})")
            self.status_label.setStyleSheet("color: #00ff00; font-style: italic;")

            # Add to database if enabled
            add_to_history = self.config.get('file_transcribe.add_to_history', True)
            if add_to_history:
                model_used = self.config.get('whisper.model', 'small')
                self.db_manager.add_transcription(
                    text=result_text,
                    language=language,
                    duration=duration,
                    model_used=model_used,
                    audio_path=self.selected_file_path,
                    source_type='file',
                    output_path=output_path
                )
                logger.info("Added file transcription to database")

            # Emit signal
            self.file_transcribed.emit({
                'text': result_text,
                'language': language,
                'duration': duration,
                'output_path': output_path,
                'output_paths': output_paths,
                'audio_file': self.selected_file_path
            })

            # Auto-open if configured
            auto_open = self.config.get('file_transcribe.auto_open_output', False)
            if auto_open and output_path:
                QDesktopServices.openUrl(QUrl.fromLocalFile(output_path))

            # Success notification
            formats_created = ", ".join([Path(p).suffix[1:].upper() for p in output_paths])
            QMessageBox.information(
                self,
                "Transcription Complete",
                f"File transcribed successfully!\n\n"
                f"Text: {len(result_text)} characters\n"
                f"Language: {language}\n"
                f"Files created: {len(output_paths)} ({formats_created})"
            )

        except Exception as e:
            logger.error(f"Error handling transcription result: {e}", exc_info=True)
            self._on_transcription_failed(str(e))

        finally:
            # Re-enable UI
            self._set_ui_enabled(True)
            self.current_job_id = None

    def _save_output_files(self, text: str, result_data: dict) -> list:
        """
        Save transcription to multiple formats based on config.

        Args:
            text: Plain text transcription
            result_data: Full Whisper result with segments

        Returns:
            List of created file paths (.txt file is always first)
        """
        try:
            audio_path = Path(self.selected_file_path)
            timestamp_duplicates = self.config.get('file_transcribe.timestamp_duplicates', True)

            # Get enabled output formats
            output_formats = self.config.get('file_transcribe.output_formats', {
                'txt': True,
                'srt': False,
                'vtt': False,
                'json': False,
                'tsv': False
            })

            # Ensure at least txt is enabled
            if not any(output_formats.values()):
                output_formats['txt'] = True
                logger.warning("No output formats enabled, defaulting to txt")

            created_files = []

            # Generate base name (with timestamp if needed)
            base_output_path = audio_path.with_suffix('.txt')
            base_name = audio_path.stem

            if base_output_path.exists() and timestamp_duplicates:
                timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                base_name = f"{audio_path.stem}_{timestamp}"
                logger.info(f"Output file exists, using timestamp: {base_name}")

            # Save each enabled format
            formatter = TranscriptionFormatter()
            for format_name, enabled in output_formats.items():
                if not enabled:
                    continue

                try:
                    # Generate output path
                    output_path = audio_path.parent / f"{base_name}.{format_name}"

                    # Convert to format
                    if format_name == 'txt':
                        content = text
                    elif format_name == 'srt':
                        content = formatter.to_srt(result_data)
                    elif format_name == 'vtt':
                        content = formatter.to_vtt(result_data)
                    elif format_name == 'json':
                        content = formatter.to_json(result_data)
                    elif format_name == 'tsv':
                        content = formatter.to_tsv(result_data)
                    else:
                        logger.warning(f"Unknown format: {format_name}")
                        continue

                    # Write file
                    logger.info(f"Writing {format_name.upper()} to: {output_path}")
                    with open(output_path, 'w', encoding='utf-8') as f:
                        f.write(content)

                    # Verify
                    if not output_path.exists():
                        logger.error(f"Failed to create {format_name} file")
                        continue

                    file_size = output_path.stat().st_size
                    logger.info(f"{format_name.upper()} saved: {file_size} bytes")

                    # Add to created files (txt first)
                    if format_name == 'txt':
                        created_files.insert(0, str(output_path))
                    else:
                        created_files.append(str(output_path))

                except Exception as e:
                    logger.error(f"Error saving {format_name} format: {e}")
                    # Continue with other formats

            if not created_files:
                raise IOError("Failed to create any output files")

            logger.info(f"Successfully created {len(created_files)} file(s)")
            return created_files

        except Exception as e:
            logger.error(f"Error saving transcription files: {e}", exc_info=True)
            raise IOError(f"Failed to save transcription: {str(e)}")

    def _on_progress_changed(self, percentage: int, message: str):
        """Handle progress update from worker"""
        self.progress_bar.setValue(percentage)
        self.status_label.setText(message)
        logger.debug(f"Progress: {percentage}% - {message}")

    def _on_transcription_complete(self, result: dict):
        """Handle successful transcription"""
        logger.info("Transcription complete")

        try:
            # Extract result data
            text = result.get('text', '')
            language = result.get('language', 'unknown')
            duration = result.get('duration', 0.0)
            output_path = result.get('output_path', '')  # Primary .txt file
            output_paths = result.get('output_paths', [output_path] if output_path else [])
            audio_file = result.get('audio_file', '')

            # Display result (only .txt content)
            self.result_text_edit.setPlainText(text)
            self.last_transcription_text = text
            self.last_output_path = output_path

            # Show all created files
            if len(output_paths) == 1:
                self.output_path_label.setText(f"Saved to: {output_paths[0]}")
            else:
                files_list = "\n  • ".join([Path(p).name for p in output_paths])
                self.output_path_label.setText(
                    f"Created {len(output_paths)} files:\n  • {files_list}"
                )

            # Enable result buttons
            self.copy_button.setEnabled(True)
            self.open_button.setEnabled(True)

            # Update status
            self.status_label.setText(f"Complete! ({len(text)} characters, {language})")
            self.status_label.setStyleSheet("color: #00ff00; font-style: italic;")

            # Add to database if enabled
            add_to_history = self.config.get('file_transcribe.add_to_history', True)
            if add_to_history:
                model_used = self.config.get('whisper.model', 'small')
                self.db_manager.add_transcription(
                    text=text,
                    language=language,
                    duration=duration,
                    model_used=model_used,
                    audio_path=audio_file,
                    source_type='file'  # Mark as file transcription
                )
                logger.info("Added file transcription to database")

            # Emit signal
            self.file_transcribed.emit(result)

            # Auto-open if configured
            auto_open = self.config.get('file_transcribe.auto_open_output', False)
            if auto_open and output_path:
                QDesktopServices.openUrl(QUrl.fromLocalFile(output_path))

            # Success notification
            formats_created = ", ".join([Path(p).suffix[1:].upper() for p in output_paths])
            QMessageBox.information(
                self,
                "Transcription Complete",
                f"File transcribed successfully!\n\n"
                f"Text: {len(text)} characters\n"
                f"Language: {language}\n"
                f"Files created: {len(output_paths)} ({formats_created})"
            )

        except Exception as e:
            logger.error(f"Error handling transcription result: {e}")

        finally:
            # Re-enable UI
            self._set_ui_enabled(True)

    def _on_transcription_failed(self, error_message: str):
        """Handle transcription error"""
        logger.error(f"Transcription failed: {error_message}")

        # Show error in UI
        self.status_label.setText(f"Error: {error_message}")
        self.status_label.setStyleSheet("color: #ff0000; font-style: italic;")

        # Re-enable UI
        self._set_ui_enabled(True)

        # Show error dialog
        QMessageBox.critical(
            self,
            "Transcription Failed",
            f"Failed to transcribe audio file:\n\n{error_message}"
        )

    def _cleanup_worker(self):
        """Clean up worker thread after completion"""
        if self.current_worker:
            self.current_worker.deleteLater()
            self.current_worker = None
        if self.current_thread:
            self.current_thread.deleteLater()
            self.current_thread = None
        logger.debug("Worker thread cleaned up")

    def _on_copy_clicked(self):
        """Handle copy to clipboard"""
        text = self.result_text_edit.toPlainText()
        if text:
            QApplication.clipboard().setText(text)
            self.status_label.setText("Copied to clipboard!")
            self.status_label.setStyleSheet("color: #00ff00; font-style: italic;")
            logger.info("Text copied to clipboard")

    def _on_open_file_clicked(self):
        """Handle open output file"""
        if self.last_output_path and Path(self.last_output_path).exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.last_output_path))
            logger.info(f"Opened output file: {self.last_output_path}")
        else:
            QMessageBox.warning(
                self,
                "File Not Found",
                "Output file no longer exists or has been moved."
            )

    def _on_clear_clicked(self):
        """Handle clear button"""
        self.selected_file_path = None
        self.last_output_path = None
        self.last_transcription_text = ""

        self.file_label.setText("No file selected")
        self.file_label.setStyleSheet("color: #888888; font-style: italic;")
        self.duration_label.setText("")
        self.result_text_edit.clear()
        self.output_path_label.setText("")
        self.status_label.setText("")
        self.status_label.setStyleSheet("color: #888888; font-style: italic;")
        self.progress_bar.setValue(0)

        self.transcribe_button.setEnabled(False)
        self.copy_button.setEnabled(False)
        self.open_button.setEnabled(False)

        logger.info("Panel cleared")

    def _set_ui_enabled(self, enabled: bool):
        """Enable/disable UI controls during transcription"""
        self.browse_button.setEnabled(enabled)
        self.transcribe_button.setEnabled(enabled and self.selected_file_path is not None)
        self.copy_button.setEnabled(enabled and bool(self.last_transcription_text))
        self.open_button.setEnabled(enabled and bool(self.last_output_path))
        self.clear_button.setEnabled(enabled)

    @staticmethod
    def _format_duration(seconds: float) -> str:
        """Format duration in seconds to MM:SS"""
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{mins}:{secs:02d}"

    # Stylesheet methods
    def _scroll_style(self) -> str:
        return """
            QScrollArea { background-color: transparent; border: none; }
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
        """

    def _group_style(self) -> str:
        return """
            QGroupBox {
                border: 1px solid #3d3d3d;
                border-radius: 8px;
                margin-top: 12px;
                padding: 12px;
                font-weight: bold;
                color: #ffffff;
                background-color: #252525;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                padding: 0 8px;
            }
        """

    def _button_style(self) -> str:
        return """
            QPushButton {
                background-color: #2d2d2d;
                border: 1px solid #3d3d3d;
                border-radius: 4px;
                padding: 8px 16px;
                color: #ffffff;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #3d3d3d;
                border-color: #4d4d4d;
            }
            QPushButton:pressed {
                background-color: #4d4d4d;
            }
            QPushButton:disabled {
                background-color: #1e1e1e;
                color: #666666;
                border-color: #2d2d2d;
            }
        """

    def _primary_button_style(self) -> str:
        return """
            QPushButton {
                background-color: #0078d4;
                border: 1px solid #0078d4;
                border-radius: 4px;
                padding: 10px 24px;
                color: #ffffff;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #005a9e;
                border-color: #005a9e;
            }
            QPushButton:pressed {
                background-color: #004578;
            }
            QPushButton:disabled {
                background-color: #1e1e1e;
                color: #666666;
                border-color: #2d2d2d;
            }
        """

    def _progress_bar_style(self) -> str:
        return """
            QProgressBar {
                border: 1px solid #3d3d3d;
                border-radius: 4px;
                background-color: #2d2d2d;
                text-align: center;
                color: #ffffff;
                height: 20px;
            }
            QProgressBar::chunk {
                background-color: #0078d4;
                border-radius: 3px;
            }
        """

    def _text_edit_style(self) -> str:
        return """
            QTextEdit {
                background-color: #2d2d2d;
                border: 1px solid #3d3d3d;
                border-radius: 4px;
                padding: 8px;
                color: #ffffff;
                font-family: 'Courier New', monospace;
                font-size: 13px;
            }
        """
