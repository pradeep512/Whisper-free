"""
macOS-specific app initialization hooks.

Called once from app.platform.platform_init(app) during WhisperFreeApp.__init__.
This is the place to wire up macOS-only things: tray icon, NSApp activation
policy, overlay collection behavior, etc.

For Phase 1, this is a stub that does nothing — later phases will populate it.
"""
import logging

logger = logging.getLogger(__name__)


def init_macos(app) -> None:
    """
    Apply macOS-specific runtime initialization.

    Args:
        app: The WhisperFreeApp instance.

    Phases that touch this:
    - Phase 3: register the menu bar tray icon, set NSApp activation policy.
    - Phase 6: apply NSWindowCollectionBehavior to the overlay.
    """
    logger.debug("init_macos: no-op stub (populated in later phases)")
