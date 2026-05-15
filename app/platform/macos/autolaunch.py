"""
macOS "Open at Login" support via SMAppService (macOS 13+).

SMAppService.mainAppService is the modern replacement for legacy
LaunchAgent plists. Registration requires the running app to be either
(a) installed in /Applications (or another standard location), or
(b) properly code-signed.

In dev mode (running from source) registration typically fails because
the host process is the Python interpreter, not a registered .app
bundle. We treat that as a benign failure — the toggle returns False
and a warning is logged.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def set_open_at_login(enabled: bool) -> bool:
    """Toggle Open-at-Login registration with macOS.

    Returns:
        True on success, False if SMAppService is unavailable or the
        registration failed (usually because we're running from source).
    """
    try:
        from ServiceManagement import SMAppService  # type: ignore[import-not-found]
    except ImportError:
        logger.warning(
            "pyobjc-framework-ServiceManagement not installed; cannot toggle "
            "Open at Login. Install with: pip install -r requirements-macos.txt"
        )
        return False

    try:
        service = SMAppService.mainAppService()
    except Exception as e:
        logger.error(f"Could not obtain SMAppService.mainAppService(): {e}")
        return False

    try:
        if enabled:
            result = service.registerAndReturnError_(None)
        else:
            result = service.unregisterAndReturnError_(None)

        # pyobjc returns a (success, error) tuple via output-param handling.
        if isinstance(result, tuple) and len(result) >= 1:
            success = bool(result[0])
            error = result[1] if len(result) > 1 else None
        else:
            success = bool(result)
            error = None

        if not success:
            logger.warning(
                f"SMAppService {'register' if enabled else 'unregister'} "
                f"failed: {error}. This is expected when running from source — "
                f"the bundled .app installed to /Applications will work."
            )
        return success
    except Exception as e:
        logger.error(f"SMAppService call raised: {e}")
        return False


def is_open_at_login_enabled() -> bool:
    """Query whether Open-at-Login is currently registered for this app."""
    try:
        from ServiceManagement import SMAppService  # type: ignore[import-not-found]
    except ImportError:
        return False

    try:
        service = SMAppService.mainAppService()
        status = service.status()
        # SMAppServiceStatusEnabled == 1 per Apple's header.
        return int(status) == 1
    except Exception as e:
        logger.debug(f"SMAppService.status() failed: {e}")
        return False
