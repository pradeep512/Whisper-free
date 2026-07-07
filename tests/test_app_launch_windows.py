"""Automated coverage for #14's last unverified acceptance criterion:
"python -m app.main launches on Windows with the main window shown (no
crash on the platform façade)".

Constructs the real WhisperFreeApp end-to-end - real ConfigManager,
DatabaseManager, AudioRecorder (sounddevice), HotkeyManager (pynput),
WhisperEngineFasterWhisper, and MainWindow - under the offscreen Qt
platform so it runs headlessly with no visible window or real global
hotkey registration. APPDATA/LOCALAPPDATA are isolated to tmp_path so the
test doesn't touch a real user's config, history DB, or model cache.

Requires network access on first run (downloads the `tiny` CTranslate2
checkpoint) - same as test_faster_whisper_engine.py.
"""

import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("faster_whisper")
pytest.importorskip("sounddevice")
pytest.importorskip("pynput")

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="exercises the Windows platform façade"
)


def test_app_launches_shows_main_window_and_cleans_up(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.delenv("HF_HOME", raising=False)

    from app.platform.windows import paths as win_paths

    # Pre-seed config with the tiny/cpu model so this doesn't download or
    # load the (much larger, GPU-hinted) 'small' default.
    config_dir = win_paths.config_dir()
    (config_dir / "config.yaml").write_text(
        "whisper:\n  model: tiny\n  device: cpu\n", encoding="utf-8"
    )

    from app.main import WhisperFreeApp

    app = WhisperFreeApp()
    try:
        assert app.main_window is not None
        app.main_window.show()
        assert app.main_window.isVisible()
    finally:
        app.cleanup()
