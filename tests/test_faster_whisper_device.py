"""Device auto-detection tests for the Windows faster-whisper backend.

These test the pure resolve_device()/compute_type_for() helpers by mocking
ctranslate2's CUDA device count, so they run on any platform/machine
regardless of whether a GPU or even ctranslate2 itself is present.
"""
import os
import sys
from unittest.mock import MagicMock, patch

from app.core.whisper_engine_faster_whisper import (
    compute_type_for,
    ensure_cuda_dlls_on_path,
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


def test_ensure_cuda_dlls_noop_when_not_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    find_spec = MagicMock()
    monkeypatch.setattr("importlib.util.find_spec", find_spec)
    ensure_cuda_dlls_on_path()
    # Bails on the platform check before ever probing for the nvidia package.
    find_spec.assert_not_called()


def test_ensure_cuda_dlls_noop_when_frozen(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    find_spec = MagicMock()
    monkeypatch.setattr("importlib.util.find_spec", find_spec)
    ensure_cuda_dlls_on_path()
    # Frozen bundle ships DLLs next to the exe; must not touch PATH here.
    find_spec.assert_not_called()


def test_ensure_cuda_dlls_adds_nvidia_bin_dirs_to_path(monkeypatch, tmp_path):
    # Simulate an installed nvidia-cublas-cu12 wheel: nvidia/cublas/bin/...
    bindir = tmp_path / "cublas" / "bin"
    bindir.mkdir(parents=True)

    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr(os, "add_dll_directory", MagicMock(), raising=False)
    monkeypatch.setenv("PATH", "")

    fake_spec = MagicMock()
    fake_spec.submodule_search_locations = [str(tmp_path)]
    monkeypatch.setattr(
        "importlib.util.find_spec",
        lambda name: fake_spec if name == "nvidia" else None,
    )

    ensure_cuda_dlls_on_path()

    assert str(bindir) in os.environ["PATH"].split(os.pathsep)
    os.add_dll_directory.assert_called_once_with(str(bindir))
