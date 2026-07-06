"""Automated coverage for #20: Windows PyInstaller onedir bundle (ffmpeg).

`app.platform.windows.init.ensure_bundled_ffmpeg_on_path()` is the runtime
seam that makes the bundle's ffmpeg.exe (packaging/windows/Whisper-Free.spec)
discoverable to audioread, which shells out to whatever `ffmpeg` resolves to
on PATH -- it never takes an explicit binary path. This is pure path/env
logic, so it's testable without a real PyInstaller build, real CUDA DLLs, or
GPU hardware; those still need a human build + smoke test per the issue's
acceptance criteria.
"""
import os
import sys

from app.platform.windows.init import ensure_bundled_ffmpeg_on_path


def test_noop_when_not_frozen(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    before = os.environ.get("PATH", "")

    assert ensure_bundled_ffmpeg_on_path() is False
    assert os.environ.get("PATH", "") == before


def test_noop_when_frozen_without_bundled_ffmpeg(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "Whisper-Free.exe"), raising=False)
    before = os.environ.get("PATH", "")

    assert ensure_bundled_ffmpeg_on_path() is False
    assert os.environ.get("PATH", "") == before


def test_prepends_bundle_dir_when_ffmpeg_present(monkeypatch, tmp_path):
    (tmp_path / "ffmpeg.exe").write_bytes(b"")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "Whisper-Free.exe"), raising=False)
    monkeypatch.setenv("PATH", r"C:\Windows\System32")

    assert ensure_bundled_ffmpeg_on_path() is True
    entries = os.environ["PATH"].split(os.pathsep)
    assert str(tmp_path) == entries[0]
    assert r"C:\Windows\System32" in entries


def test_does_not_duplicate_path_entry_if_called_twice(monkeypatch, tmp_path):
    (tmp_path / "ffmpeg.exe").write_bytes(b"")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "Whisper-Free.exe"), raising=False)
    monkeypatch.setenv("PATH", r"C:\Windows\System32")

    ensure_bundled_ffmpeg_on_path()
    ensure_bundled_ffmpeg_on_path()

    assert os.environ["PATH"].split(os.pathsep).count(str(tmp_path)) == 1
