"""
Platform façade. Re-exports OS-specific implementations.

Call sites import from this module without caring about the OS:
    from app.platform import paths
    config = paths.config_file()

The actual implementation is in app.platform.linux, app.platform.macos, or
app.platform.windows.
"""
import sys

if sys.platform == 'darwin':
    from app.platform.macos import paths
    from app.platform.macos import hotkey_perms
    from app.platform.macos import autolaunch
elif sys.platform.startswith('linux'):
    from app.platform.linux import paths
    from app.platform.linux import hotkey_perms
    from app.platform.linux import autolaunch
elif sys.platform == 'win32':
    # Windows has no autolaunch/tray submodule yet (tracked separately);
    # hotkey_perms + paths are enough for first-light launch + transcription.
    from app.platform.windows import paths
    from app.platform.windows import hotkey_perms
else:
    raise RuntimeError(
        f"Unsupported platform: {sys.platform}. "
        "Whisper-Free supports Linux, macOS (Apple Silicon), and Windows."
    )


def set_dock_visible(visible: bool) -> bool:
    """Toggle the macOS Dock icon. No-op on non-darwin platforms (returns True).

    Args:
        visible: True to show the Dock icon (Regular policy),
                 False to hide it (Accessory policy, default for agent apps).

    Returns:
        True on success or when not applicable; False if the call failed.
    """
    if sys.platform == 'darwin':
        try:
            from app.platform.macos.init import set_dock_visible as _impl
            return _impl(visible)
        except ImportError:
            return False
    return True


def apply_early_config(config) -> None:
    """Apply per-platform config tweaks BEFORE core components are built.

    Called from WhisperFreeApp.__init__ right after ConfigManager loads,
    BEFORE HotkeyManager and other components read the config. Must be
    cheap and dependency-free.

    Args:
        config: The ConfigManager instance.
    """
    if sys.platform == 'darwin':
        try:
            from app.platform.macos import init as macos_init
            macos_init.apply_early_macos_config(config)
        except ImportError:
            # macOS-specific deps not installed; degrade silently.
            pass


def platform_init(app) -> None:
    """
    Apply per-platform runtime initialization to the WhisperFreeApp instance.

    Called once at the END of WhisperFreeApp.__init__, after components exist
    but before the event loop starts. Used for things like installing the
    macOS tray icon, setting NSApp activation policy, applying overlay
    collection behavior.

    Args:
        app: The WhisperFreeApp instance.
    """
    if sys.platform == 'darwin':
        try:
            from app.platform.macos import init as macos_init
            macos_init.init_macos(app)
        except ImportError:
            # macOS-specific deps not installed; degrade gracefully.
            pass
    # Linux currently has nothing extra to do at init time.


__all__ = [
    'paths', 'hotkey_perms', 'autolaunch',
    'apply_early_config', 'platform_init', 'set_dock_visible',
]
