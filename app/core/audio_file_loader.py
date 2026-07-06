"""
AudioFileLoader - Load and process Media files (audio or video) for Whisper transcription

This module provides utilities to load audio formats and video containers,
converting them to the format expected by WhisperEngine (16kHz mono float32
numpy array). "Media file" (audio or video) is the canonical user-facing term
- see CONTEXT.md. The class keeps its historical `AudioFileLoader` name (see
CONTEXT.md note) to avoid churn.

Audio formats: MP3, WAV, M4A, FLAC, OGG, OPUS, WebM - decoded via librosa
(audioread -> ffmpeg where needed), unchanged.

Video containers: MP4, MOV, MKV, AVI, WebM, M4V, FLV, WMV, MPEG, MPG, TS,
3GP - decoded via an explicit ffmpeg subprocess to a temporary 16kHz mono
WAV, then loaded via the existing fast path and deleted. See
docs/adr/0002-video-decode-via-ffmpeg.md for why video gets its own path.

Requires: librosa, soundfile, audioread, ffmpeg (system dependency)

Author: Whisper-Free Project
License: MIT
"""

import numpy as np
from pathlib import Path
from typing import Tuple, Optional
import logging
import os
import shutil
import subprocess
import tempfile

logger = logging.getLogger(__name__)


class AudioLoadError(Exception):
    """Custom exception for audio loading errors"""
    pass


class AudioFileLoader:
    """
    Load and process Media files (audio or video) for Whisper transcription.

    Handles various audio formats and video containers, converting them to
    16kHz mono float32.
    """

    # Audio formats - decoded via the existing librosa path, unchanged.
    AUDIO_FORMATS = ['.mp3', '.wav', '.m4a', '.flac', '.ogg', '.opus', '.webm']

    # Video containers - decoded via an explicit ffmpeg subprocess (see
    # docs/adr/0002-video-decode-via-ffmpeg.md). Note '.webm' also appears in
    # AUDIO_FORMATS; is_video() below resolves the overlap in favor of the
    # existing audio path so audio-only .webm files are unaffected.
    VIDEO_FORMATS = [
        '.mp4', '.mov', '.mkv', '.avi', '.webm', '.m4v', '.flv', '.wmv',
        '.mpeg', '.mpg', '.ts', '.3gp',
    ]

    # Union of both, preserving AUDIO_FORMATS first and de-duplicating.
    # (Built with a plain loop, not a comprehension: class-body
    # comprehensions can't see sibling class attributes like AUDIO_FORMATS.)
    SUPPORTED_FORMATS = list(AUDIO_FORMATS)
    for _fmt in VIDEO_FORMATS:
        if _fmt not in SUPPORTED_FORMATS:
            SUPPORTED_FORMATS.append(_fmt)
    del _fmt

    TARGET_SAMPLE_RATE = 16000  # Whisper requirement

    # Formats that work without ffmpeg (using soundfile)
    SOUNDFILE_FORMATS = ['.wav', '.flac', '.ogg']

    # Formats that require ffmpeg
    FFMPEG_FORMATS = ['.mp3', '.m4a', '.opus', '.webm']

    @staticmethod
    def get_dialog_filter() -> str:
        """
        Build the shared file-dialog filter string for Media files (audio
        and video), derived from SUPPORTED_FORMATS so every panel offers
        the same formats as the loader actually accepts. Includes an
        "All Files" escape hatch for exotic containers.

        Returns:
            A Qt QFileDialog-style filter string, e.g.
            "Media Files (*.mp3 *.wav ... *.mp4 ...);;All Files (*.*)"
        """
        patterns = " ".join(f"*{fmt}" for fmt in AudioFileLoader.SUPPORTED_FORMATS)
        return f"Media Files ({patterns});;All Files (*.*)"

    @staticmethod
    def is_video(file_path: str) -> bool:
        """
        Check whether a file should be decoded via the video (ffmpeg
        subprocess) path rather than the existing audio (librosa) path.

        Args:
            file_path: Path to a Media file

        Returns:
            True if the file's extension is video-only (i.e. in
            VIDEO_FORMATS and not also in AUDIO_FORMATS).
        """
        suffix = Path(file_path).suffix.lower()
        return suffix in AudioFileLoader.VIDEO_FORMATS and suffix not in AudioFileLoader.AUDIO_FORMATS

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
        Load a Media file (audio or video) and convert to 16kHz mono
        float32 numpy array.

        Video files are routed to VideoAudioExtractor, which decodes them
        via an explicit ffmpeg subprocess to a temporary WAV, loads that
        WAV through this same method (the existing fast path), and deletes
        the temp file. Audio files keep the existing librosa path below,
        unchanged.

        Args:
            file_path: Path to a Media file

        Returns:
            Numpy array of shape (samples,) with dtype float32
            Values are in range [-1.0, 1.0]

        Raises:
            AudioLoadError: If file cannot be loaded
        """
        if AudioFileLoader.is_video(file_path):
            is_valid, error_msg = AudioFileLoader.validate_file(file_path)
            if not is_valid:
                raise AudioLoadError(error_msg)
            logger.info(f"Loading video Media file via ffmpeg extraction: {file_path}")
            return VideoAudioExtractor.extract_and_load(file_path)

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


class VideoAudioExtractor:
    """
    Extracts the audio track of a video Media file to a temporary 16kHz
    mono WAV via an explicit ffmpeg subprocess, per
    docs/adr/0002-video-decode-via-ffmpeg.md.

    This is deliberately a separate decode path from the librosa/audioread
    path used for audio formats: audioread is slow and fragile on long
    media, and video files skew long.
    """

    @staticmethod
    def extract_to_wav(file_path: str) -> str:
        """
        Extract the audio track of a video file into a temporary 16kHz
        mono WAV file using ffmpeg.

        Args:
            file_path: Path to the source video file

        Returns:
            Path to a temporary .wav file. The caller is responsible for
            deleting it (extract_and_load does this automatically).

        Raises:
            AudioLoadError: If ffmpeg cannot be found or extraction fails.
                Any temp file created before the failure is removed.
        """
        ffmpeg_path = shutil.which("ffmpeg")
        if not ffmpeg_path:
            raise AudioLoadError(
                "Cannot extract audio from video: ffmpeg was not found on PATH.\n\n"
                "Install ffmpeg and ensure it is on PATH, or use the installed "
                "Windows build, which bundles ffmpeg."
            )

        fd, temp_wav_path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)

        cmd = [
            ffmpeg_path,
            "-y",
            "-i", file_path,
            "-ar", str(AudioFileLoader.TARGET_SAMPLE_RATE),
            "-ac", "1",
            "-f", "wav",
            temp_wav_path,
        ]

        try:
            logger.info(f"Extracting audio from video via ffmpeg: {' '.join(cmd)}")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                raise AudioLoadError(
                    "ffmpeg failed to extract audio from video "
                    f"(exit code {result.returncode}):\n{result.stderr.strip()}"
                )
        except Exception:
            VideoAudioExtractor._safe_remove(temp_wav_path)
            raise

        return temp_wav_path

    @staticmethod
    def extract_and_load(file_path: str) -> np.ndarray:
        """
        Extract a video's audio track to a temp WAV, load it via the
        existing fast (soundfile-backed) WAV path, and delete the temp
        file - including when the load step itself fails.

        Args:
            file_path: Path to the source video file

        Returns:
            Numpy array of shape (samples,) with dtype float32

        Raises:
            AudioLoadError: If extraction or loading fails.
        """
        temp_wav_path = VideoAudioExtractor.extract_to_wav(file_path)
        try:
            return AudioFileLoader.load_audio(temp_wav_path)
        finally:
            VideoAudioExtractor._safe_remove(temp_wav_path)

    @staticmethod
    def _safe_remove(path: str) -> None:
        """Best-effort removal of a temp file; never raises."""
        try:
            if path and os.path.exists(path):
                os.remove(path)
        except OSError as e:
            logger.warning(f"Could not remove temp file {path}: {e}")


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
