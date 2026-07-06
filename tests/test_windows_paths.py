"""Path resolution tests for app.platform.windows.paths.

Windows-only path helpers; skipped on other platforms since they aren't
importable there (no win32-specific deps, just guarded by sys.platform
conventions the module itself doesn't enforce, but the semantics —
%APPDATA%/%LOCALAPPDATA% — only make sense on win32).
"""
import sys

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != 'win32', reason="Windows-only path conventions"
)


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    appdata = tmp_path / "Roaming"
    localappdata = tmp_path / "Local"
    monkeypatch.setenv("APPDATA", str(appdata))
    monkeypatch.setenv("LOCALAPPDATA", str(localappdata))
    monkeypatch.delenv("HF_HOME", raising=False)
    return appdata, localappdata


def test_config_file_under_appdata(isolated_env):
    from app.platform.windows import paths

    appdata, _ = isolated_env
    assert paths.config_file() == appdata / "Whisper-Free" / "config.yaml"
    assert paths.config_file().parent.is_dir()


def test_database_file_under_appdata(isolated_env):
    from app.platform.windows import paths

    appdata, _ = isolated_env
    assert paths.database_file() == appdata / "Whisper-Free" / "history.db"


def test_models_dir_under_localappdata_and_sets_hf_home(isolated_env, monkeypatch):
    from app.platform.windows import paths

    _, localappdata = isolated_env
    models_dir = paths.models_dir()
    assert models_dir == localappdata / "Whisper-Free" / "models"
    assert models_dir.is_dir()
    assert os_environ_has_hf_home(models_dir)


def os_environ_has_hf_home(models_dir):
    import os
    return os.environ.get("HF_HOME") == str(models_dir)


def test_log_file_under_localappdata(isolated_env):
    from app.platform.windows import paths

    _, localappdata = isolated_env
    assert paths.log_file() == localappdata / "Whisper-Free" / "logs" / "whisper-free.log"


def test_install_hint_ffmpeg_is_windows_flavored():
    from app.platform.windows import paths

    hint = paths.install_hint_ffmpeg()
    assert "winget" in hint or "ffmpeg.org" in hint
