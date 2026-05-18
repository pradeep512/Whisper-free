"""
macOS path conventions per Apple's File System Programming Guide.

- Config:  ~/Library/Application Support/Whisper-Free/config.yaml
- DB:      ~/Library/Application Support/Whisper-Free/history.db
- Models:  ~/Library/Caches/Whisper-Free/models/   (re-downloadable; excluded
           from Time Machine and iCloud backups)
- Logs:    ~/Library/Logs/Whisper-Free/whisper-free.log
"""
import subprocess
from pathlib import Path

_APP_NAME = "Whisper-Free"


def _app_support_dir() -> Path:
    p = Path.home() / "Library" / "Application Support" / _APP_NAME
    p.mkdir(parents=True, exist_ok=True)
    return p


def _caches_dir() -> Path:
    p = Path.home() / "Library" / "Caches" / _APP_NAME
    p.mkdir(parents=True, exist_ok=True)
    return p


def _logs_dir() -> Path:
    p = Path.home() / "Library" / "Logs" / _APP_NAME
    p.mkdir(parents=True, exist_ok=True)
    return p


def config_dir() -> Path:
    return _app_support_dir()


def config_file() -> Path:
    return config_dir() / "config.yaml"


def database_file() -> Path:
    return config_dir() / "history.db"


def models_dir() -> Path:
    """Where MLX Whisper checkpoints live (HuggingFace cache target)."""
    p = _caches_dir() / "models"
    p.mkdir(parents=True, exist_ok=True)
    return p


def log_file() -> Path:
    return _logs_dir() / "whisper-free.log"


def reveal_in_finder(path: Path) -> None:
    """Open Finder at the given path's parent, with the path itself selected."""
    subprocess.run(['open', '-R', str(path)], check=False)


def open_url(url: str) -> None:
    """Open a URL or x-apple.systempreferences:... deep link."""
    subprocess.run(['open', url], check=False)


def install_hint_ffmpeg() -> str:
    """Human-readable hint for installing ffmpeg on this platform."""
    return "brew install ffmpeg"
