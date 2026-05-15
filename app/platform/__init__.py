"""
Platform façade. Re-exports OS-specific implementations.

Call sites import from this module without caring about the OS:
    from app.platform import paths
    config = paths.config_file()

The actual implementation is in app.platform.linux or app.platform.macos.
"""
import sys

if sys.platform == 'darwin':
    from app.platform.macos import paths
elif sys.platform.startswith('linux'):
    from app.platform.linux import paths
else:
    raise RuntimeError(
        f"Unsupported platform: {sys.platform}. "
        "Whisper-Free supports Linux and macOS (Apple Silicon) only."
    )


def platform_init(app) -> None:
    """
    Apply per-platform initialization to the WhisperFreeApp instance.

    Called once during WhisperFreeApp.__init__ after components exist but
    before the event loop starts. Used for things like installing the
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
            # Pre-Phase 3, this path is the norm.
            pass
    # Linux currently has nothing extra to do at init time.


__all__ = ['paths', 'platform_init']
