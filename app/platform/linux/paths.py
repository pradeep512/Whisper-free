"""
Linux path conventions per XDG Base Directory Specification.

Mirrors the historical Whisper-Free paths:
- Config:  ~/.config/whisper-free/config.yaml
- DB:      ~/.config/whisper-free/history.db
- Models:  ~/.cache/whisper/  (managed by openai-whisper)
- Logs:    ~/.config/whisper-free/whisper-free.log
"""
import os
import subprocess
from pathlib import Path

_APP_DIRNAME = "whisper-free"


def config_dir() -> Path:
    base = os.environ.get('XDG_CONFIG_HOME') or str(Path.home() / '.config')
    p = Path(base) / _APP_DIRNAME
    p.mkdir(parents=True, exist_ok=True)
    return p


def config_file() -> Path:
    return config_dir() / 'config.yaml'


def database_file() -> Path:
    return config_dir() / 'history.db'


def models_dir() -> Path:
    """Where Whisper model checkpoints live.

    On Linux we don't override; openai-whisper uses ~/.cache/whisper/ which
    is fine. Returned for parity with the macOS API.
    """
    base = os.environ.get('XDG_CACHE_HOME') or str(Path.home() / '.cache')
    p = Path(base) / 'whisper'
    p.mkdir(parents=True, exist_ok=True)
    return p


def log_file() -> Path:
    return config_dir() / 'whisper-free.log'


def reveal_in_finder(path: Path) -> None:
    """Open the file manager at the given path's parent."""
    subprocess.run(['xdg-open', str(path.parent)], check=False)


def open_url(url: str) -> None:
    """Open a URL in the default browser."""
    subprocess.run(['xdg-open', url], check=False)


def install_hint_ffmpeg() -> str:
    """Human-readable hint for installing ffmpeg on this platform."""
    return "sudo apt-get install ffmpeg"
