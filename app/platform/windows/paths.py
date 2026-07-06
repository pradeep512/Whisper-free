"""
Windows path conventions.

- Config:  %APPDATA%\\Whisper-Free\\config.yaml
- DB:      %APPDATA%\\Whisper-Free\\history.db
- Models:  %LOCALAPPDATA%\\Whisper-Free\\models\\   (large, re-downloadable;
           kept out of the roaming profile so they never sync)
- Logs:    %LOCALAPPDATA%\\Whisper-Free\\logs\\whisper-free.log

HF_HOME is pointed at the models dir so huggingface_hub (used by
faster-whisper to pull CTranslate2 checkpoints) caches there instead of the
user's home directory.
"""
import os
import subprocess
from pathlib import Path

_APP_NAME = "Whisper-Free"


def _appdata_dir() -> Path:
    base = os.environ.get('APPDATA') or str(Path.home() / 'AppData' / 'Roaming')
    p = Path(base) / _APP_NAME
    p.mkdir(parents=True, exist_ok=True)
    return p


def _localappdata_dir() -> Path:
    base = os.environ.get('LOCALAPPDATA') or str(Path.home() / 'AppData' / 'Local')
    p = Path(base) / _APP_NAME
    p.mkdir(parents=True, exist_ok=True)
    return p


def config_dir() -> Path:
    return _appdata_dir()


def config_file() -> Path:
    return config_dir() / "config.yaml"


def database_file() -> Path:
    return config_dir() / "history.db"


def models_dir() -> Path:
    """Where CTranslate2 Whisper checkpoints live (HF_HOME target)."""
    p = _localappdata_dir() / "models"
    p.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault('HF_HOME', str(p))
    return p


def log_file() -> Path:
    p = _localappdata_dir() / "logs"
    p.mkdir(parents=True, exist_ok=True)
    return p / "whisper-free.log"


def reveal_in_finder(path: Path) -> None:
    """Open Explorer with the given path selected."""
    subprocess.run(['explorer', '/select,', str(path)], check=False)


def open_url(url: str) -> None:
    """Open a URL (or ms-settings: deep link) with the default handler."""
    os.startfile(url)  # type: ignore[attr-defined]


def install_hint_ffmpeg() -> str:
    """Human-readable hint for installing ffmpeg on this platform.

    Not normally needed — the packaged app bundles ffmpeg.exe. This hint is
    only surfaced when running from source without it on PATH.
    """
    return "winget install ffmpeg (or download from ffmpeg.org and add to PATH)"
