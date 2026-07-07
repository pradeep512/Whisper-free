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
from typing import List, Tuple, Optional
import logging
import os
import platform
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

    # Soft "this may be slow" threshold for very long Media files (#27).
    # Whole-file (non-chunked) transcription is retained regardless; this
    # only gates a warning so the user can decide whether to proceed.
    LONG_MEDIA_WARNING_THRESHOLD_SECONDS = 3 * 60 * 60  # 3 hours

    @staticmethod
    def ffmpeg_missing_message(context: str = "") -> str:
        """
        Build an OS-aware, directly-assertable message explaining that
        ffmpeg could not be found or used (#27). Replaces the historical
        Linux-only "sudo apt-get install ffmpeg" guidance, which was wrong
        on Windows and misleading for MP3/M4A/OPUS/WebM audio.

        Args:
            context: Optional short description of what needed ffmpeg
                (e.g. "MP4 file", "MP3 file") to prefix the message with.

        Returns:
            A user-facing, multi-line string with OS-appropriate guidance.
        """
        prefix = f"Cannot process {context}: " if context else ""
        if platform.system() == "Windows":
            return (
                f"{prefix}ffmpeg could not be found.\n\n"
                "The installed Whisper-Free app ships with ffmpeg bundled, "
                "so this normally only happens when running from source.\n\n"
                "If you are running from source: install ffmpeg "
                "(https://ffmpeg.org/download.html), make sure it is on "
                "your PATH, then restart Whisper-Free."
            )
        return (
            f"{prefix}ffmpeg could not be found.\n\n"
            "Install ffmpeg using your package manager, e.g.:\n"
            "  macOS:          brew install ffmpeg\n"
            "  Debian/Ubuntu:  sudo apt-get install ffmpeg\n"
            "  Fedora:         sudo dnf install ffmpeg\n\n"
            "Then make sure it is on your PATH and restart Whisper-Free."
        )

    @staticmethod
    def ffmpeg_available() -> bool:
        """Lightweight probe: is an ffmpeg binary resolvable on PATH?"""
        return shutil.which("ffmpeg") is not None

    @staticmethod
    def requires_ffmpeg(file_path: str) -> bool:
        """
        Whether loading this Media file needs ffmpeg: any video, or a
        compressed audio format (FFMPEG_FORMATS) that librosa/audioread
        shells out to ffmpeg for.
        """
        suffix = Path(file_path).suffix.lower()
        return AudioFileLoader.is_video(file_path) or suffix in AudioFileLoader.FFMPEG_FORMATS

    @staticmethod
    def should_warn_missing_ffmpeg(file_paths: List[str]) -> bool:
        """
        Pre-flight decision (#27): should a single up-front warning be
        shown before starting a run (single-file or Batch) over these
        queued files?

        True only when ffmpeg cannot be resolved on PATH *and* at least
        one queued file would actually need it to load. Runtime failures
        for files that don't need ffmpeg still fall through to the
        existing per-file Failed/retry/details UI.
        """
        if AudioFileLoader.ffmpeg_available():
            return False
        return any(AudioFileLoader.requires_ffmpeg(p) for p in file_paths)

    @staticmethod
    def is_long_media(duration_seconds: float) -> bool:
        """Soft "this may be slow" check for very long Media files (#27)."""
        return duration_seconds >= AudioFileLoader.LONG_MEDIA_WARNING_THRESHOLD_SECONDS

    @staticmethod
    def long_media_warning_message(duration_seconds: float) -> str:
        """
        Build the soft warning shown before transcribing a very long
        Media file. Whole-file behavior (no chunking) is retained; this
        only informs so the user can decide whether to proceed.
        """
        hours = duration_seconds / 3600.0
        return (
            f"This Media file is about {hours:.1f} hours long.\n\n"
            "Transcribing very long files can take a while and use "
            "significant memory - the whole file is processed in one "
            "pass (no chunking).\n\n"
            "Do you want to continue?"
        )

    # Substrings ffmpeg emits on stderr when a container has no audio
    # stream to extract - matched case-insensitively.
    _NO_AUDIO_STREAM_MARKERS = (
        "does not contain any stream",
        "matches no streams",
        "stream map '0:a' matches no streams",
    )

    @staticmethod
    def looks_like_no_audio_stream(ffmpeg_stderr: str) -> bool:
        """
        Heuristic: does this ffmpeg stderr output indicate the input has
        no audio track (rather than some other decode failure)? Used so
        a video with no audio track fails with a clear, specific message
        instead of a generic ffmpeg error dump (#27).
        """
        lowered = (ffmpeg_stderr or "").lower()
        return any(marker in lowered for marker in AudioFileLoader._NO_AUDIO_STREAM_MARKERS)

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
                            AudioFileLoader.ffmpeg_missing_message(
                                f"{path.suffix.upper()} file"
                            )
                            + "\n\nFormats that work without ffmpeg: WAV, FLAC, OGG"
                        )

                raise AudioLoadError(
                    f"Failed to load audio file: {error_msg}\n\n"
                    "This may require ffmpeg for certain formats.\n\n"
                    + AudioFileLoader.ffmpeg_missing_message()
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
                            AudioFileLoader.ffmpeg_missing_message(
                                f"{path.suffix.upper()} file"
                            )
                        )

                raise AudioLoadError(
                    f"Failed to get audio duration: {error_msg}\n\n"
                    + AudioFileLoader.ffmpeg_missing_message()
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
                AudioFileLoader.ffmpeg_missing_message(f"{Path(file_path).suffix.upper()} video")
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
                stderr = (result.stderr or "").strip()
                if AudioFileLoader.looks_like_no_audio_stream(stderr):
                    raise AudioLoadError(
                        f"This video has no audio track to transcribe: "
                        f"{Path(file_path).name}"
                    )
                raise AudioLoadError(
                    "ffmpeg failed to extract audio from video "
                    f"(exit code {result.returncode}):\n{stderr}"
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
