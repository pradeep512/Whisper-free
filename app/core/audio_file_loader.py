"""
AudioFileLoader - Load and process audio files for Whisper transcription

This module provides utilities to load various audio formats and convert them
to the format expected by WhisperEngine (16kHz mono float32 numpy array).

Supports: MP3, WAV, M4A, FLAC, OGG, OPUS, WebM
Requires: librosa, soundfile, audioread, ffmpeg (system dependency)

Author: Whisper-Free Project
License: MIT
"""

import numpy as np
from pathlib import Path
from typing import Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class AudioLoadError(Exception):
    """Custom exception for audio loading errors"""
    pass


class AudioFileLoader:
    """
    Load and process audio files for Whisper transcription.

    Handles various audio formats and converts to 16kHz mono float32.
    """

    SUPPORTED_FORMATS = ['.mp3', '.wav', '.m4a', '.flac', '.ogg', '.opus', '.webm']
    TARGET_SAMPLE_RATE = 16000  # Whisper requirement

    # Formats that work without ffmpeg (using soundfile)
    SOUNDFILE_FORMATS = ['.wav', '.flac', '.ogg']

    # Formats that require ffmpeg
    FFMPEG_FORMATS = ['.mp3', '.m4a', '.opus', '.webm']

    @staticmethod
    def is_supported(file_path: str) -> bool:
        """
        Check if file format is supported.

        Args:
            file_path: Path to audio file

        Returns:
            True if format is supported, False otherwise
        """
        try:
            path = Path(file_path)
            return path.suffix.lower() in AudioFileLoader.SUPPORTED_FORMATS
        except Exception as e:
            logger.error(f"Error checking file format: {e}")
            return False

    @staticmethod
    def validate_file(file_path: str) -> Tuple[bool, str]:
        """
        Validate audio file before loading.

        Args:
            file_path: Path to audio file

        Returns:
            (is_valid, error_message) tuple
            - is_valid: True if file can be loaded
            - error_message: Empty if valid, error description otherwise
        """
        try:
            path = Path(file_path)

            # Check file exists
            if not path.exists():
                return False, f"File does not exist: {file_path}"

            # Check file is not a directory
            if path.is_dir():
                return False, "Path is a directory, not a file"

            # Check file is readable
            if not path.is_file():
                return False, "Path is not a regular file"

            try:
                with open(path, 'rb') as f:
                    pass
            except PermissionError:
                return False, "Cannot read file (permission denied)"
            except Exception as e:
                return False, f"Cannot access file: {str(e)}"

            # Check format is supported
            if not AudioFileLoader.is_supported(file_path):
                supported = ", ".join(AudioFileLoader.SUPPORTED_FORMATS)
                return False, f"Unsupported format '{path.suffix}'. Supported: {supported}"

            # Check file is not empty
            if path.stat().st_size == 0:
                return False, "File is empty (0 bytes)"

            return True, ""

        except Exception as e:
            logger.error(f"Error validating file: {e}")
            return False, f"Validation error: {str(e)}"

    @staticmethod
    def load_audio(file_path: str) -> np.ndarray:
        """
        Load audio file and convert to 16kHz mono float32 numpy array.

        Args:
            file_path: Path to audio file

        Returns:
            Numpy array of shape (samples,) with dtype float32
            Values are in range [-1.0, 1.0]

        Raises:
            AudioLoadError: If file cannot be loaded
        """
        try:
            # Import here to provide better error messages if missing
            try:
                import librosa
            except ImportError:
                raise AudioLoadError(
                    "librosa not installed. Install with: pip install librosa soundfile audioread"
                )

            # Validate before loading
            is_valid, error_msg = AudioFileLoader.validate_file(file_path)
            if not is_valid:
                raise AudioLoadError(error_msg)

            logger.info(f"Loading audio file: {file_path}")

            # Load audio using librosa
            # sr=None loads at native sample rate, then we resample
            # mono=False to handle stereo properly, then we'll convert
            try:
                audio, sr = librosa.load(
                    file_path,
                    sr=AudioFileLoader.TARGET_SAMPLE_RATE,  # Resample to 16kHz
                    mono=True,  # Convert to mono
                    dtype=np.float32
                )
            except Exception as e:
                error_msg = str(e) if str(e) else repr(e)
                logger.error(f"librosa load error: {error_msg}", exc_info=True)

                # Check if this is a backend error (no ffmpeg)
                path = Path(file_path)
                if 'NoBackendError' in repr(e) or 'NoBackend' in error_msg or not error_msg:
                    if path.suffix.lower() in AudioFileLoader.FFMPEG_FORMATS:
                        raise AudioLoadError(
                            f"Cannot load {path.suffix.upper()} file: ffmpeg is not installed.\n\n"
                            f"Install ffmpeg:\n"
                            f"  sudo apt-get install ffmpeg\n\n"
                            f"Or convert to WAV format:\n"
                            f"  ffmpeg -i '{path.name}' -ar 16000 -ac 1 output.wav\n\n"
                            f"Formats that work without ffmpeg: WAV, FLAC, OGG"
                        )

                raise AudioLoadError(
                    f"Failed to load audio file: {error_msg}\n\n"
                    f"This may require ffmpeg for certain formats.\n"
                    f"Install: sudo apt-get install ffmpeg"
                )

            # Verify output format
            if audio.ndim != 1:
                raise AudioLoadError(f"Expected 1D array, got shape {audio.shape}")

            if audio.dtype != np.float32:
                logger.warning(f"Converting from {audio.dtype} to float32")
                audio = audio.astype(np.float32)

            # Verify sample rate
            if sr != AudioFileLoader.TARGET_SAMPLE_RATE:
                logger.warning(f"Sample rate is {sr}, expected {AudioFileLoader.TARGET_SAMPLE_RATE}")
                # Resample if needed
                audio = librosa.resample(
                    audio,
                    orig_sr=sr,
                    target_sr=AudioFileLoader.TARGET_SAMPLE_RATE
                )

            logger.info(
                f"Loaded audio: {len(audio)} samples, "
                f"{len(audio)/AudioFileLoader.TARGET_SAMPLE_RATE:.2f}s duration"
            )

            return audio

        except AudioLoadError:
            raise
        except Exception as e:
            logger.error(f"Unexpected error loading audio: {e}", exc_info=True)
            raise AudioLoadError(f"Failed to load audio: {str(e)}")

    @staticmethod
    def get_duration(file_path: str) -> float:
        """
        Get audio duration in seconds without full load.

        Args:
            file_path: Path to audio file

        Returns:
            Duration in seconds

        Raises:
            AudioLoadError: If duration cannot be determined
        """
        try:
            import librosa

            # Validate file first
            is_valid, error_msg = AudioFileLoader.validate_file(file_path)
            if not is_valid:
                raise AudioLoadError(error_msg)

            # Get duration efficiently without loading full audio
            try:
                duration = librosa.get_duration(path=file_path)
                logger.debug(f"Audio duration: {duration:.2f}s")
                return duration
            except Exception as e:
                error_msg = str(e) if str(e) else repr(e)
                logger.error(f"Error getting duration: {error_msg}", exc_info=True)

                # Check if this is a backend error (no ffmpeg)
                path = Path(file_path)
                if 'NoBackendError' in repr(e) or 'NoBackend' in error_msg or not error_msg:
                    if path.suffix.lower() in AudioFileLoader.FFMPEG_FORMATS:
                        raise AudioLoadError(
                            f"Cannot get duration for {path.suffix.upper()} file: ffmpeg is not installed.\n\n"
                            f"Install: sudo apt-get install ffmpeg"
                        )

                raise AudioLoadError(
                    f"Failed to get audio duration: {error_msg}\n\n"
                    f"Install ffmpeg: sudo apt-get install ffmpeg"
                )

        except AudioLoadError:
            raise
        except ImportError:
            raise AudioLoadError("librosa not installed")
        except Exception as e:
            logger.error(f"Unexpected error getting duration: {e}")
            raise AudioLoadError(f"Failed to get duration: {str(e)}")


# Example usage
if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) < 2:
        print("Usage: python audio_file_loader.py <audio_file>")
        sys.exit(1)

    file_path = sys.argv[1]

    # Validate
    is_valid, error = AudioFileLoader.validate_file(file_path)
    print(f"Valid: {is_valid}")
    if not is_valid:
        print(f"Error: {error}")
        sys.exit(1)

    # Get duration
    try:
        duration = AudioFileLoader.get_duration(file_path)
        print(f"Duration: {duration:.2f}s")
    except AudioLoadError as e:
        print(f"Error getting duration: {e}")

    # Load audio
    try:
        audio = AudioFileLoader.load_audio(file_path)
        print(f"Loaded: {audio.shape}, {audio.dtype}")
        print(f"Range: [{audio.min():.3f}, {audio.max():.3f}]")
    except AudioLoadError as e:
        print(f"Error loading: {e}")
        sys.exit(1)
