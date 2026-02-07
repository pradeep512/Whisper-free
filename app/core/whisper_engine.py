"""
WhisperEngine: Manages Whisper model lifecycle and transcription.

This module provides a GPU-optimized interface to OpenAI's Whisper model for
real-time voice transcription. Designed for RTX 4060 8GB with VRAM efficiency.

Author: Whisper-Free Project
License: MIT
"""

import whisper
import torch
import numpy as np
from typing import Optional, Dict, Any
import logging
import io
import pkgutil
from functools import lru_cache

# Configure logging
logger = logging.getLogger(__name__)


def _patch_whisper_assets() -> None:
    """
    Ensure Whisper assets (mel_filters.npz) load correctly in packaged builds.

    In some frozen environments, file-based assets may not be found even though
    they are bundled. This patch adds a fallback that loads the asset from the
    package data via pkgutil when the file path is missing.
    """
    try:
        from whisper import audio as whisper_audio
    except Exception:
        return

    if getattr(whisper_audio, "_wf_patched", False):
        return

    original = whisper_audio.mel_filters

    @lru_cache(maxsize=None)
    def mel_filters(device, n_mels: int):
        try:
            return original(device, n_mels)
        except FileNotFoundError:
            data = pkgutil.get_data("whisper", "assets/mel_filters.npz")
            if data is None:
                raise
            with np.load(io.BytesIO(data), allow_pickle=False) as f:
                return torch.from_numpy(f[f"mel_{n_mels}"]).to(device)

    whisper_audio.mel_filters = mel_filters
    whisper_audio._wf_patched = True


class WhisperEngine:
    """
    Manages Whisper model lifecycle and transcription.
    Keeps model in VRAM for fast repeated use.

    Optimized for RTX 4060 8GB (target VRAM: ~1.5-3 GB for small/medium models)

    Attributes:
        model_name (str): Current loaded model size
        device (str): Device being used ('cuda' or 'cpu')
        model: Loaded Whisper model instance

    Example:
        >>> engine = WhisperEngine(model_name="small", device="cuda")
        >>> audio = np.random.randn(16000 * 10).astype(np.float32)  # 10 seconds
        >>> result = engine.transcribe(audio)
        >>> print(result['text'])
        >>> engine.cleanup()
    """

    # Valid Whisper model sizes
    VALID_MODELS = ['tiny', 'base', 'small', 'medium', 'large', 'large-v3-turbo']

    # Estimated VRAM requirements (in GB)
    # Based on OpenAI docs + overhead
    MODEL_VRAM_REQS = {
        'tiny': 1.0,
        'base': 1.5,
        'small': 2.0,
        'medium': 5.0,
        'large': 10.0,
        'large-v3-turbo': 6.0
    }

    def __init__(self, model_name: str = "small", device: str = "cuda"):
        """
        Initialize WhisperEngine with specified model.

        Args:
            model_name: Whisper model size (tiny/base/small/medium/large-v3-turbo)
                       - tiny: ~1GB VRAM, fastest, least accurate
                       - base: ~1.5GB VRAM, fast, decent accuracy
                       - small: ~2GB VRAM, good balance (RECOMMENDED)
                       - medium: ~5GB VRAM, high accuracy, slower
                       - large-v3-turbo: ~6GB VRAM, best accuracy, slowest
            device: "cuda" or "cpu"

        Raises:
            RuntimeError: If CUDA requested but not available
            ValueError: If model_name is invalid
        """
        self.model_name = None
        self.device = device
        self.model = None

        # Validate device
        if device == "cuda" and not torch.cuda.is_available():
            error_msg = (
                "CUDA device requested but not available. "
                "Please check your PyTorch installation and GPU drivers. "
                "Falling back to CPU mode may be very slow."
            )
            logger.error(error_msg)
            raise RuntimeError(error_msg)

        # Log device info
        if device == "cuda":
            gpu_name = torch.cuda.get_device_name(0)
            total_vram = torch.cuda.get_device_properties(0).total_memory / (1024**3)
            logger.info(f"Using GPU: {gpu_name} with {total_vram:.1f} GB VRAM")
        else:
            logger.info("Using CPU for inference (this will be slow)")

        # Validate and load model
        if model_name not in self.VALID_MODELS:
            error_msg = (
                f"Invalid model_name: '{model_name}'. "
                f"Must be one of: {', '.join(self.VALID_MODELS)}"
            )
            logger.error(error_msg)
            raise ValueError(error_msg)

        # Patch asset loading for frozen builds
        _patch_whisper_assets()

        # Load the model
        self._load_model(model_name)

    def _load_model(self, model_name: str) -> None:
        """
        Internal method to load a Whisper model.

        Args:
            model_name: Model size to load

        Raises:
            RuntimeError: If model loading fails
        """
        logger.info(f"Loading Whisper model '{model_name}' on {self.device}...")

        try:
            # Load model (downloads on first use)
            self.model = whisper.load_model(model_name, device=self.device)
            self.model_name = model_name

            # Log VRAM usage if on GPU
            if self.device == "cuda":
                vram_mb = self.get_vram_usage()
                logger.info(
                    f"Model '{model_name}' loaded successfully. "
                    f"VRAM usage: {vram_mb:.1f} MB"
                )
            else:
                logger.info(f"Model '{model_name}' loaded successfully on CPU")

        except Exception as e:
            error_msg = f"Failed to load model '{model_name}': {str(e)}"
            logger.error(error_msg, exc_info=True)
            raise RuntimeError(error_msg) from e

    def transcribe(
        self,
        audio_array: np.ndarray,
        language: Optional[str] = None,
        task: str = "transcribe",
        **kwargs
    ) -> Dict[str, Any]:
        """
        Transcribe audio array (must be 16kHz mono float32).
        ...（docstring omitted for brevity)...
        """
        # Validate inputs
        if audio_array is None:
            raise ValueError("audio_array cannot be None")

        if not isinstance(audio_array, np.ndarray):
            raise ValueError(
                f"audio_array must be a numpy array, got {type(audio_array)}"
            )

        if audio_array.size == 0:
            raise ValueError("audio_array is empty (size == 0)")

        if audio_array.ndim != 1:
            raise ValueError(
                f"audio_array must be 1D (mono), got shape {audio_array.shape}. "
                "If you have stereo audio, convert to mono first."
            )

        # Ensure float32
        if audio_array.dtype != np.float32:
            logger.debug(f"Converting audio from {audio_array.dtype} to float32")
            audio_array = audio_array.astype(np.float32)

        # Calculate duration
        duration = len(audio_array) / 16000.0
        logger.info(
            f"Starting transcription: {duration:.2f}s audio, "
            f"language={'auto-detect' if language is None else language}, "
            f"task={task}"
        )

        try:
            # Transcribe with default options overridden by kwargs
            transcribe_options = {
                'language': language,
                'task': task,
                'fp16': self.device == 'cuda',  # Use FP16 on GPU for speed
                'beam_size': 1,  # Greedy decoding (fastest)
                'temperature': 0.0,  # Deterministic output
                'condition_on_previous_text': False,  # Avoid hallucinations on short clips
                'verbose': False,  # Reduce console spam
            }

            # Update with provided kwargs
            transcribe_options.update(kwargs)

            # Remove None values
            transcribe_options = {k: v for k, v in transcribe_options.items() if v is not None}

            result = self.model.transcribe(audio_array, **transcribe_options)

            # Build response
            response = {
                'text': result['text'].strip(),
                'language': result.get('language', language or 'unknown'),
                'segments': result.get('segments', []),
                'duration': duration
            }

            logger.info(
                f"Transcription complete: '{response['text'][:100]}...' "
                f"({len(response['text'])} chars, {len(response['segments'])} segments)"
            )

            return response

        except torch.cuda.OutOfMemoryError as e:
            error_msg = (
                f"CUDA out of memory during transcription. "
                f"Current model: {self.model_name}. "
                f"Try using a smaller model (tiny/base/small) or free up GPU memory."
            )
            logger.error(error_msg, exc_info=True)
            raise RuntimeError(error_msg) from e

        except Exception as e:
            error_msg = f"Transcription failed: {str(e)}"
            logger.error(error_msg, exc_info=True)
            raise RuntimeError(error_msg) from e

    def change_model(self, model_name: str) -> None:
        """
        Hot-swap to a different model size without restart.
        Releases old model from VRAM before loading new one.

        This is useful for switching between fast/accurate models on the fly.

        Args:
            model_name: New model size to load (tiny/base/small/medium/large-v3-turbo)

        Raises:
            ValueError: If model_name is invalid

        Example:
            >>> engine.change_model('medium')  # Switch to higher accuracy
            >>> result = engine.transcribe(audio)
            >>> engine.change_model('tiny')    # Switch back to speed
        """
        if model_name == self.model_name:
            logger.info(f"Model '{model_name}' is already loaded, skipping reload")
            return

        if model_name not in self.VALID_MODELS:
            error_msg = (
                f"Invalid model_name: '{model_name}'. "
                f"Must be one of: {', '.join(self.VALID_MODELS)}"
            )
            logger.error(error_msg)
            raise ValueError(error_msg)

        logger.info(f"Changing model from '{self.model_name}' to '{model_name}'...")

        # Release old model
        old_vram = self.get_vram_usage() if self.device == "cuda" else 0.0

        if self.model is not None:
            del self.model
            self.model = None

        # Clear GPU cache
        if self.device == "cuda":
            torch.cuda.empty_cache()
            logger.debug(f"Released {old_vram:.1f} MB VRAM from old model")

        # Load new model
        self._load_model(model_name)

        logger.info(f"Model changed successfully to '{model_name}'")

    def get_vram_usage(self) -> float:
        """
        Get current VRAM usage in MB.

        Returns:
            VRAM usage in MB (0.0 if CPU mode)
        """
        if self.device == "cuda" and torch.cuda.is_available():
            # Get allocated memory in bytes, convert to MB
            allocated_bytes = torch.cuda.memory_allocated()
            allocated_mb = allocated_bytes / (1024 * 1024)
            return allocated_mb
        return 0.0

    @staticmethod
    def get_available_vram() -> float:
        """
        Get total available VRAM on primary GPU in GB.

        Returns:
            Total VRAM in GB (0.0 if no CUDA)
        """
        if torch.cuda.is_available():
            try:
                props = torch.cuda.get_device_properties(0)
                return props.total_memory / (1024**3)
            except Exception as e:
                logger.error(f"Error getting VRAM info: {e}")
                return 0.0
        return 0.0

    def cleanup(self) -> None:
        """
        Release GPU memory and clean up resources.
        Call this before application exit.

        Example:
            >>> engine.cleanup()
            >>> # GPU memory is now freed
        """
        logger.info("Cleaning up WhisperEngine resources...")

        if self.model is not None:
            vram_before = self.get_vram_usage()
            del self.model
            self.model = None

            if self.device == "cuda":
                torch.cuda.empty_cache()
                logger.info(f"Released {vram_before:.1f} MB VRAM")

        self.model_name = None
        logger.info("WhisperEngine cleanup complete")

    def __del__(self):
        """Destructor to ensure cleanup on garbage collection."""
        try:
            if hasattr(self, 'model') and self.model is not None:
                self.cleanup()
        except Exception as e:
            # Don't raise exceptions in destructor
            logger.debug(f"Error in destructor: {e}")

    def __repr__(self) -> str:
        """String representation of the engine state."""
        vram = f", VRAM: {self.get_vram_usage():.1f}MB" if self.device == "cuda" else ""
        return (
            f"WhisperEngine(model='{self.model_name}', "
            f"device='{self.device}'{vram})"
        )
