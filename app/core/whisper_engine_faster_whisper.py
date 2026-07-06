"""
WhisperEngineFasterWhisper: Windows Whisper backend using faster-whisper (CTranslate2).

Public surface mirrors WhisperEngine / WhisperEngineMLX so the rest of the app
(queue manager, PTT path, file/batch transcription, settings UI) is unchanged.

Device is auto-detected (CUDA if an NVIDIA GPU is available, else CPU) unless
overridden. Compute type is chosen per device: float16 on CUDA, int8 on CPU —
this is what keeps CPU-only Windows machines (the common case) fast.

Models are CTranslate2 checkpoints pulled from the HuggingFace Hub on first
use; ctranslate2/faster-whisper resolve them via huggingface_hub, which
honors HF_HOME (pointed at our models dir by app.platform.windows.paths).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import numpy as np

logger = logging.getLogger(__name__)


def resolve_device() -> str:
    """Return 'cuda' if an NVIDIA GPU is available to CTranslate2, else 'cpu'."""
    try:
        import ctranslate2

        if ctranslate2.get_cuda_device_count() > 0:
            return "cuda"
    except Exception as e:
        logger.debug(f"CUDA device probe failed, falling back to CPU: {e}")
    return "cpu"


def compute_type_for(device: str) -> str:
    """Precision to use per device — float16 on GPU, int8 on CPU."""
    return "float16" if device == "cuda" else "int8"


def resolve_effective_device(requested: Optional[str] = None) -> str:
    """Resolve the device to actually use, given a caller-requested hint.

    'cpu' is always honored exactly — it's the explicit override Settings
    exposes to force CPU. Anything else (None, 'cuda', 'auto') auto-detects:
    CUDA if an NVIDIA GPU is available, else CPU. This matters because
    `whisper.device` defaults to 'cuda' (a Linux-era default shared across
    platforms) — most Windows machines have no NVIDIA GPU, so a bare 'cuda'
    request must degrade to CPU rather than fail to load the model.
    """
    if requested == "cpu":
        return "cpu"
    return resolve_device()


class WhisperEngineFasterWhisper:
    """Windows Whisper backend (faster-whisper / CTranslate2).

    Differences vs the Linux torch WhisperEngine that callers should be
    aware of:
    - `device` defaults to auto-detected CUDA-or-CPU rather than requiring
      the caller to pick; pass device='cpu' to force CPU. A 'cuda' request
      with no GPU present degrades to CPU (with a warning) instead of
      raising, since `whisper.device` shares Linux's 'cuda' default.
    - VRAM reporting is best-effort (CTranslate2 doesn't expose a precise
      per-model VRAM counter the way torch does); returns 0.0 when unknown.
    """

    VALID_MODELS = ['tiny', 'base', 'small', 'medium', 'large', 'large-v3-turbo']

    # Approximate memory footprint per model in GB (CTranslate2 checkpoints).
    MODEL_VRAM_REQS = {
        'tiny': 0.5,
        'base': 0.7,
        'small': 1.2,
        'medium': 2.5,
        'large': 4.5,
        'large-v3-turbo': 2.5,
    }

    def __init__(self, model_name: str = "small", device: Optional[str] = None):
        if model_name not in self.VALID_MODELS:
            raise ValueError(
                f"Invalid model_name: '{model_name}'. "
                f"Must be one of: {', '.join(self.VALID_MODELS)}"
            )

        try:
            from app.platform import paths
            paths.models_dir()  # side effect: sets HF_HOME
        except Exception as e:
            logger.warning(f"Could not set HF_HOME: {e}")

        self.device = resolve_effective_device(device)
        if device == "cuda" and self.device == "cpu":
            logger.warning(
                "whisper.device='cuda' requested but no NVIDIA GPU was detected; "
                "falling back to CPU"
            )
        self.compute_type = compute_type_for(self.device)
        self.model_name: Optional[str] = None
        self.model = None

        self._load_model(model_name)

    # -------- lifecycle --------

    def _load_model(self, model_name: str) -> None:
        from faster_whisper import WhisperModel

        logger.info(
            f"Loading faster-whisper model '{model_name}' "
            f"on {self.device} ({self.compute_type})..."
        )
        try:
            self.model = WhisperModel(
                model_name,
                device=self.device,
                compute_type=self.compute_type,
            )
            self.model_name = model_name
            logger.info(f"faster-whisper model '{model_name}' ready")
        except Exception as e:
            error_msg = f"Failed to load model '{model_name}': {e}"
            logger.error(error_msg, exc_info=True)
            raise RuntimeError(error_msg) from e

    def cleanup(self) -> None:
        """Release the model. CTranslate2 frees native resources on GC."""
        logger.info("Cleaning up WhisperEngineFasterWhisper")
        self.model = None
        self.model_name = None

    def __del__(self):
        try:
            if self.model is not None:
                self.cleanup()
        except Exception:
            pass

    # -------- inference --------

    def transcribe(
        self,
        audio_array: np.ndarray,
        language: Optional[str] = None,
        task: str = "transcribe",
        **kwargs,
    ) -> Dict[str, Any]:
        """Transcribe a 16 kHz mono float32 audio array.

        Returns:
            {
                'text': str,
                'language': str,
                'segments': list[dict],  # each has at least 'end'
                'duration': float,       # audio length in seconds
            }
        """
        if audio_array is None:
            raise ValueError("audio_array cannot be None")
        if not isinstance(audio_array, np.ndarray):
            raise ValueError(
                f"audio_array must be a numpy array, got {type(audio_array)}"
            )
        if audio_array.size == 0:
            raise ValueError("audio_array is empty")
        if audio_array.ndim != 1:
            raise ValueError(
                f"audio_array must be 1-D mono, got shape {audio_array.shape}"
            )
        if audio_array.dtype != np.float32:
            audio_array = audio_array.astype(np.float32)

        if self.model is None:
            raise RuntimeError(
                "WhisperEngineFasterWhisper has no model loaded. "
                "Call change_model() first."
            )

        duration = len(audio_array) / 16000.0
        logger.info(
            f"faster-whisper transcribe: {duration:.2f}s audio, "
            f"language={'auto' if language is None else language}, task={task}"
        )

        try:
            segments_iter, info = self.model.transcribe(
                audio_array,
                language=language,
                task=task,
                temperature=kwargs.get('temperature', 0.0),
            )
            segments = [
                {
                    'id': i,
                    'start': seg.start,
                    'end': seg.end,
                    'text': seg.text,
                }
                for i, seg in enumerate(segments_iter)
            ]
        except Exception as e:
            logger.error(f"faster-whisper transcription failed: {e}", exc_info=True)
            raise RuntimeError(f"Transcription failed: {e}") from e

        text = "".join(seg['text'] for seg in segments).strip()
        response = {
            'text': text,
            'language': getattr(info, 'language', None) or language or 'unknown',
            'segments': segments,
            'duration': duration,
        }
        logger.info(
            f"faster-whisper transcribe complete: {len(text)} chars, "
            f"{len(segments)} segments"
        )
        return response

    # -------- model management --------

    def change_model(self, model_name: str) -> None:
        """Hot-swap the active model. No-op if already loaded."""
        if model_name == self.model_name:
            logger.info(f"Model '{model_name}' already loaded; skipping")
            return
        if model_name not in self.VALID_MODELS:
            raise ValueError(
                f"Invalid model_name: '{model_name}'. "
                f"Must be one of: {', '.join(self.VALID_MODELS)}"
            )
        logger.info(f"Changing model: '{self.model_name}' -> '{model_name}'")
        self.model = None
        self._load_model(model_name)

    # -------- introspection --------

    def get_vram_usage(self) -> float:
        """Best-effort VRAM usage in MB. CTranslate2 doesn't expose a precise
        counter; returns the static estimate for the loaded model on CUDA,
        or 0.0 on CPU / when unknown."""
        if self.device != "cuda" or self.model_name is None:
            return 0.0
        return self.MODEL_VRAM_REQS.get(self.model_name, 0.0) * 1024

    @staticmethod
    def get_available_vram() -> float:
        """Return total VRAM of GPU 0 in GB, or 0.0 if no CUDA device.

        CTranslate2 doesn't expose a VRAM query itself; this is a best-effort
        check via pynvml when available, degrading to 0.0 otherwise (the
        overlay/status display treats 0.0 as "unknown" and falls back to CPU
        display, per WhisperEngineFasterWhisper's device auto-detect).
        """
        try:
            import ctranslate2

            if ctranslate2.get_cuda_device_count() == 0:
                return 0.0
        except Exception:
            return 0.0
        try:
            import pynvml  # type: ignore[import-not-found]

            pynvml.nvmlInit()
            handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            total = pynvml.nvmlDeviceGetMemoryInfo(handle).total
            return total / (1024 ** 3)
        except Exception:
            return 0.0

    def __repr__(self) -> str:
        vram = f", VRAM~{self.get_vram_usage():.0f}MB" if self.device == "cuda" else ""
        return (
            f"WhisperEngineFasterWhisper(model={self.model_name!r}, "
            f"device='{self.device}'{vram})"
        )
