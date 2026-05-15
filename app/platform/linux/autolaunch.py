"""
Linux "Open at Login" support via XDG autostart.

Writes a .desktop file to $XDG_CONFIG_HOME/autostart/ (default
~/.config/autostart/) which most desktop environments (GNOME, KDE,
XFCE) honor at login.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_AUTOSTART_FILENAME = "whisper-free.desktop"


def _autostart_dir() -> Path:
    base = os.environ.get('XDG_CONFIG_HOME') or str(Path.home() / '.config')
    p = Path(base) / 'autostart'
    p.mkdir(parents=True, exist_ok=True)
    return p


def _autostart_path() -> Path:
    return _autostart_dir() / _AUTOSTART_FILENAME


_DESKTOP_FILE = """[Desktop Entry]
Type=Application
Name=Whisper-Free
Exec=whisper
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
Comment=Local, privacy-first speech-to-text
Categories=AudioVideo;Utility;
"""


def set_open_at_login(enabled: bool) -> bool:
    """Toggle the XDG autostart entry."""
    path = _autostart_path()
    if enabled:
        try:
            path.write_text(_DESKTOP_FILE)
            logger.info(f"Created autostart entry: {path}")
            return True
        except Exception as e:
            logger.error(f"Could not write autostart file {path}: {e}")
            return False
    else:
        try:
            if path.exists():
                path.unlink()
                logger.info(f"Removed autostart entry: {path}")
            return True
        except Exception as e:
            logger.error(f"Could not remove autostart file {path}: {e}")
            return False


def is_open_at_login_enabled() -> bool:
    return _autostart_path().exists()
