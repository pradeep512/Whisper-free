"""
WhisperEngineMLX: Apple Silicon Whisper backend using mlx-whisper.

Public surface mirrors WhisperEngine so the rest of the app (queue manager,
PTT path, file/batch transcription, settings UI) is unchanged.

This module imports mlx_whisper lazily because on Linux the package is not
installed; we want `import app.core.whisper_engine_mlx` to succeed even on
Linux so the factory in whisper_engine.py can reference it.

Requires:
    - Apple Silicon (M1+)
    - macOS 13.5+
    - Python 3.10+
    - mlx >= 0.20.0
    - mlx-whisper >= 0.4.0
    - huggingface_hub
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

import numpy as np

logger = logging.getLogger(__name__)


# MLX model repos on HuggingFace Hub. Verified naming as of port doc:
# https://huggingface.co/mlx-community
MLX_MODEL_REPOS: Dict[str, str] = {
    'tiny':           'mlx-community/whisper-tiny-mlx',
    'base':           'mlx-community/whisper-base-mlx',
    'small':          'mlx-community/whisper-small-mlx',
    'medium':         'mlx-community/whisper-medium-mlx',
    'large':          'mlx-community/whisper-large-v3-mlx',
    'large-v3-turbo': 'mlx-community/whisper-large-v3-turbo',
}


class WhisperEngineMLX:
    """Apple Silicon Whisper backend.

    The public API matches WhisperEngine so callers (TranscriptionQueueManager,
    SettingsPanel, main.py) work without conditional code.

    Differences vs the CUDA WhisperEngine that callers should be aware of:
    - `device` is always "mlx"; ignored as a parameter.
    - `fp16` kwarg is silently ignored (MLX manages precision internally).
    - VRAM is unified memory; `get_vram_usage()` reports MLX's active memory.
    - Models are downloaded lazily from HuggingFace Hub on first `transcribe()`
      call. We pre-warm in `__init__` to keep first PTT latency low.
    """

    VALID_MODELS = list(MLX_MODEL_REPOS.keys())

    # Approximate memory footprint per model in GB (unified memory).
    # MLX is more compact than the PyTorch checkpoints.
    MODEL_VRAM_REQS = {
        'tiny':            0.4,
        'base':            0.7,
        'small':           1.2,
        'medium':          2.5,
        'large':           5.5,
        'large-v3-turbo':  3.2,
    }

    def __init__(self, model_name: str = "small", device: str = "mlx"):
        if model_name not in self.VALID_MODELS:
            raise ValueError(
                f"Invalid model_name: '{model_name}'. "
                f"Must be one of: {', '.join(self.VALID_MODELS)}"
            )

        self.device = "mlx"  # canonical name; mlx is the only backend here
        self.model_name: Optional[str] = None
        self.model_path: Optional[str] = None

        # Redirect HuggingFace cache to our caches dir. mlx-whisper resolves
        # model files via huggingface_hub which honors HF_HOME.
        try:
            from app.platform import paths
            hf_cache = str(paths.models_dir() / "huggingface")
            os.environ.setdefault('HF_HOME', hf_cache)
            logger.debug(f"HF_HOME -> {hf_cache}")
        except Exception as e:
            logger.warning(f"Could not set HF_HOME: {e}")

        self._load_model(model_name)

    # -------- lifecycle --------

    def _load_model(self, model_name: str) -> None:
        """Set the model to use and pre-warm by running a tiny silent inference.

        mlx-whisper's high-level transcribe() loads the model lazily and
        caches it via an internal LRU. Pre-warming here means the first real
        PTT inference doesn't pay the download + load cost.
        """
        repo = MLX_MODEL_REPOS[model_name]
        logger.info(f"Loading MLX model: {repo}")

        self.model_path = repo
        self.model_name = model_name

        # Pre-warm: feed a 100ms silent buffer through transcribe() so the
        # model is loaded into unified memory before the first real PTT.
        # We swallow errors — if the network is down, we'll fail loudly on
        # the first real transcribe() call instead.
        try:
            self._prewarm()
        except Exception as e:
            logger.warning(
                f"MLX model pre-warm failed (model will load on first use): {e}"
            )

        logger.info(f"MLX model '{model_name}' ready ({repo})")

    def _prewarm(self) -> None:
        """Run a tiny inference to force model load into memory."""
        import mlx_whisper

        silent_audio = np.zeros(int(16000 * 0.1), dtype=np.float32)
        mlx_whisper.transcribe(
            silent_audio,
            path_or_hf_repo=self.model_path,
            verbose=False,
        )

    def cleanup(self) -> None:
        """Release model from memory.

        mlx-whisper holds the model in its internal LRU cache; we can clear
        Metal's active memory by deallocating MLX arrays. The actual cache
        eviction is best-effort — relying on Python GC is sufficient for our
        use case (shutdown).
        """
        logger.info("Cleaning up WhisperEngineMLX")
        try:
            import mlx.core as mx
            # MLX exposes clear_cache on newer versions; guard for older ones.
            if hasattr(mx, 'clear_cache'):
                mx.clear_cache()
            elif hasattr(mx, 'metal') and hasattr(mx.metal, 'clear_cache'):
                mx.metal.clear_cache()
        except Exception as e:
            logger.debug(f"MLX cache clear skipped: {e}")

        self.model_path = None
        self.model_name = None

    def __del__(self):
        try:
            if self.model_path is not None:
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

        Args:
            audio_array: 1-D numpy array, 16 kHz mono, float32 in [-1, 1].
            language: ISO 639-1 code (e.g. 'en') or None to auto-detect.
            task: 'transcribe' or 'translate'.
            **kwargs: Whisper options. We pass through `temperature` and
                ignore unsupported ones (`fp16`, `beam_size`,
                `condition_on_previous_text`) — mlx-whisper manages these
                internally or doesn't expose them.

        Returns:
            {
                'text': str,
                'language': str,
                'segments': list[dict],
                'duration': float,  # audio length in seconds
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

        if self.model_path is None:
            raise RuntimeError(
                "WhisperEngineMLX has no model loaded. Call change_model() first."
            )

        duration = len(audio_array) / 16000.0
        logger.info(
            f"MLX transcribe: {duration:.2f}s audio, "
            f"language={'auto' if language is None else language}, task={task}"
        )

        # Import here so module-load on Linux doesn't fail.
        import mlx_whisper

        try:
            result = mlx_whisper.transcribe(
                audio_array,
                path_or_hf_repo=self.model_path,
                language=language,
                task=task,
                temperature=kwargs.get('temperature', 0.0),
                verbose=False,
            )
        except Exception as e:
            logger.error(f"MLX transcription failed: {e}", exc_info=True)
            raise RuntimeError(f"Transcription failed: {e}") from e

        text = (result.get('text') or '').strip()
        response = {
            'text': text,
            'language': result.get('language', language or 'unknown'),
            'segments': result.get('segments', []),
            'duration': duration,
        }
        logger.info(
            f"MLX transcribe complete: {len(text)} chars, "
            f"{len(response['segments'])} segments"
        )
        return response

    # -------- model management --------

    def change_model(self, model_name: str) -> None:
        """Hot-swap the active model. No-op if already loaded."""
        if model_name == self.model_name:
            logger.info(f"MLX model '{model_name}' already loaded; skipping")
            return
        if model_name not in self.VALID_MODELS:
            raise ValueError(
                f"Invalid model_name: '{model_name}'. "
                f"Must be one of: {', '.join(self.VALID_MODELS)}"
            )
        logger.info(f"Changing MLX model: '{self.model_name}' -> '{model_name}'")
        # Free old model's cache before loading the new one.
        try:
            import mlx.core as mx
            if hasattr(mx, 'clear_cache'):
                mx.clear_cache()
            elif hasattr(mx, 'metal') and hasattr(mx.metal, 'clear_cache'):
                mx.metal.clear_cache()
        except Exception:
            pass
        self._load_model(model_name)

    # -------- introspection --------

    def get_vram_usage(self) -> float:
        """Return MLX active memory in MB (unified memory on Apple Silicon)."""
        try:
            import mlx.core as mx
            # Prefer the newer API; fall back to the metal namespace.
            if hasattr(mx, 'get_active_memory'):
                return mx.get_active_memory() / (1024 * 1024)
            if hasattr(mx, 'metal') and hasattr(mx.metal, 'get_active_memory'):
                return mx.metal.get_active_memory() / (1024 * 1024)
        except Exception as e:
            logger.debug(f"get_vram_usage failed: {e}")
        return 0.0

    @staticmethod
    def get_available_vram() -> float:
        """Return total available unified memory on this Mac, in GB."""
        try:
            import subprocess
            out = subprocess.check_output(['sysctl', '-n', 'hw.memsize']).strip()
            return int(out) / (1024 ** 3)
        except Exception as e:
            logger.warning(f"Could not query unified memory size: {e}")
            return 0.0

    def __repr__(self) -> str:
        return (
            f"WhisperEngineMLX(model={self.model_name!r}, device='mlx', "
            f"active_memory={self.get_vram_usage():.0f} MB)"
        )
