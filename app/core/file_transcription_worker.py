"""
FileTranscriptionWorker - Background worker for transcribing audio files

This worker runs file transcription in a separate QThread to prevent UI freezing.
Handles the complete workflow: validate -> load -> transcribe -> save .txt file.

Author: Whisper-Free Project
License: MIT
"""

from PySide6.QtCore import QObject, Signal
from pathlib import Path
from datetime import datetime
import logging
import traceback
from typing import List, Dict, Any

from app.core.audio_file_loader import AudioFileLoader, AudioLoadError
from app.core.transcription_formats import convert_transcription

logger = logging.getLogger(__name__)


class FileTranscriptionWorker(QObject):
    """
    QThread worker for transcribing audio files.

    Signals:
        progress_changed(int, str): Progress percentage (0-100) and status message
        transcription_complete(dict): Result dict with keys:
            - text: str
            - language: str
            - duration: float
            - output_path: str
            - audio_file: str
        transcription_failed(str): Error message
    """

    # Signals
    progress_changed = Signal(int, str)  # (percentage, status_message)
    transcription_complete = Signal(dict)  # result dict
    transcription_failed = Signal(str)  # error_message

    def __init__(self, file_path: str, whisper_engine, config_manager):
        """
        Initialize worker.

        Args:
            file_path: Path to audio file to transcribe
            whisper_engine: WhisperEngine instance
            config_manager: ConfigManager instance
        """
        super().__init__()
        self.file_path = file_path
        self.whisper_engine = whisper_engine
        self.config = config_manager

        logger.info(f"FileTranscriptionWorker initialized for: {file_path}")

    def run(self):
        """
        Main worker method - runs in background thread.

        Process:
        1. Validate file (5%)
        2. Load audio (20%)
        3. Transcribe (60%)
        4. Save .txt file (80%)
        5. Complete (100%)
        """
        try:
            logger.info("Starting file transcription workflow...")

            # Step 1: Validate file (5%)
            self.progress_changed.emit(5, "Validating audio file...")
            is_valid, error_msg = AudioFileLoader.validate_file(self.file_path)
            if not is_valid:
                raise AudioLoadError(error_msg)

            # Get duration for reporting
            try:
                duration = AudioFileLoader.get_duration(self.file_path)
                logger.info(f"Audio duration: {duration:.2f}s")
            except Exception as e:
                logger.warning(f"Could not get duration: {e}")
                duration = 0.0

            # Step 2: Load audio (20%)
            self.progress_changed.emit(20, "Loading audio file...")
            audio_data = AudioFileLoader.load_audio(self.file_path)
            logger.info(f"Audio loaded: {len(audio_data)} samples")

            # Step 3: Transcribe (40% -> 80% range)
            self.progress_changed.emit(40, "Transcribing audio...")

            # Get transcription settings from config
            language = self.config.get('whisper.language', None)
            settings = {
                'fp16': self.config.get('whisper.fp16', True),
                'beam_size': self.config.get('whisper.beam_size', 1),
                'temperature': self.config.get('whisper.temperature', 0.0)
            }

            logger.info(f"Transcription settings: language={language}, {settings}")

            # Transcribe using WhisperEngine
            result = self.whisper_engine.transcribe(
                audio_data,
                language=language,
                **settings
            )

            text = result.get('text', '').strip()
            detected_language = result.get('language', 'unknown')

            if not text:
                text = "[No speech detected]"
                logger.warning("No speech detected in audio")

            logger.info(f"Transcription complete: {len(text)} chars, language={detected_language}")

            # Step 4: Save to output file(s) (80%)
            self.progress_changed.emit(80, "Saving transcription...")
            output_paths = self._save_transcription(result, text)
            main_output_path = output_paths[0] if output_paths else ""
            logger.info(f"Transcription saved to {len(output_paths)} file(s)")

            # Step 5: Complete (100%)
            self.progress_changed.emit(100, "Complete!")

            # Build result dict
            result_dict = {
                'text': text,
                'language': detected_language,
                'duration': duration,
                'output_path': main_output_path,  # Primary .txt file
                'output_paths': output_paths,  # All created files
                'audio_file': self.file_path
            }

            # Emit success signal
            self.transcription_complete.emit(result_dict)

            logger.info("File transcription workflow complete")

        except AudioLoadError as e:
            error_msg = f"Audio loading error: {str(e)}"
            logger.error(error_msg)
            self.transcription_failed.emit(error_msg)

        except Exception as e:
            error_msg = f"Transcription failed: {str(e)}"
            logger.error(f"{error_msg}\n{traceback.format_exc()}")
            self.transcription_failed.emit(error_msg)

    def _save_transcription(self, result: Dict[str, Any], text: str) -> List[str]:
        """
        Save transcription to multiple formats based on config.

        Formats:
        - txt: Plain text
        - srt: SRT subtitles
        - vtt: WebVTT subtitles
        - json: Full JSON data
        - tsv: Tab-separated values

        Args:
            result: Full Whisper transcription result (with segments)
            text: Plain text transcription

        Returns:
            List of paths to all created files (txt file is always first)

        Raises:
            IOError: If files cannot be written
        """
        try:
            audio_path = Path(self.file_path)
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
            for format_name, enabled in output_formats.items():
                if not enabled:
                    continue

                try:
                    # Generate output path
                    output_path = audio_path.parent / f"{base_name}.{format_name}"

                    # Convert to format
                    if format_name == 'txt':
                        content = text
                    else:
                        content = convert_transcription(result, format_name)

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
            logger.error(f"Error saving transcription: {e}", exc_info=True)
            raise IOError(f"Failed to save transcription: {str(e)}")


# Standalone test
if __name__ == "__main__":
    import sys
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QThread

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("FileTranscriptionWorker test")
    print("Note: Requires WhisperEngine and ConfigManager mocks")
    print("Use integration test instead")
