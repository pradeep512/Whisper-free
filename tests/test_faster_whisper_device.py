"""Device auto-detection tests for the Windows faster-whisper backend.

These test the pure resolve_device()/compute_type_for() helpers by mocking
ctranslate2's CUDA device count, so they run on any platform/machine
regardless of whether a GPU or even ctranslate2 itself is present.
"""
from unittest.mock import MagicMock, patch

from app.core.whisper_engine_faster_whisper import (
    compute_type_for,
    resolve_device,
    resolve_effective_device,
)


def test_resolve_device_prefers_cuda_when_gpu_available():
    fake_ct2 = MagicMock()
    fake_ct2.get_cuda_device_count.return_value = 1
    with patch.dict("sys.modules", {"ctranslate2": fake_ct2}):
        assert resolve_device() == "cuda"


def test_resolve_device_falls_back_to_cpu_when_no_gpu():
    fake_ct2 = MagicMock()
    fake_ct2.get_cuda_device_count.return_value = 0
    with patch.dict("sys.modules", {"ctranslate2": fake_ct2}):
        assert resolve_device() == "cpu"


def test_resolve_device_falls_back_to_cpu_on_import_error():
    with patch.dict("sys.modules", {"ctranslate2": None}):
        assert resolve_device() == "cpu"


def test_compute_type_for_cuda_is_float16():
    assert compute_type_for("cuda") == "float16"


def test_compute_type_for_cpu_is_int8():
    assert compute_type_for("cpu") == "int8"


def test_resolve_effective_device_honors_explicit_cpu_even_with_gpu_available():
    fake_ct2 = MagicMock()
    fake_ct2.get_cuda_device_count.return_value = 1
    with patch.dict("sys.modules", {"ctranslate2": fake_ct2}):
        assert resolve_effective_device("cpu") == "cpu"


def test_resolve_effective_device_falls_back_to_cpu_for_cuda_request_without_gpu():
    # whisper.device defaults to 'cuda' (shared with Linux) — most Windows
    # machines have no NVIDIA GPU, so this must degrade gracefully.
    fake_ct2 = MagicMock()
    fake_ct2.get_cuda_device_count.return_value = 0
    with patch.dict("sys.modules", {"ctranslate2": fake_ct2}):
        assert resolve_effective_device("cuda") == "cpu"


def test_resolve_effective_device_uses_cuda_request_when_gpu_available():
    fake_ct2 = MagicMock()
    fake_ct2.get_cuda_device_count.return_value = 1
    with patch.dict("sys.modules", {"ctranslate2": fake_ct2}):
        assert resolve_effective_device("cuda") == "cuda"


def test_resolve_effective_device_auto_detects_when_none():
    fake_ct2 = MagicMock()
    fake_ct2.get_cuda_device_count.return_value = 1
    with patch.dict("sys.modules", {"ctranslate2": fake_ct2}):
        assert resolve_effective_device(None) == "cuda"
