"""
macOS-specific app initialization hooks.

Called once from `app.platform.platform_init(app)` during
`WhisperFreeApp.__init__`, after components exist but before the event
loop starts.

Responsibilities:
- Set NSApp activation policy to "accessory" so the Dock icon is hidden
  even when running from source (the bundled .app uses Info.plist's
  LSUIElement=true; this call is what makes dev runs match that behavior).
- Construct and wire the menu bar TrayController.
- Override the hotkey defaults on first launch to Mac-appropriate keys.

Future phases:
- Phase 6: apply NSWindowCollectionBehavior to the overlay so it shows
  across Spaces / full-screen apps.
- Phase 4: trigger the onboarding wizard on first launch.
"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def apply_early_macos_config(config) -> None:
    """Apply macOS-specific config tweaks BEFORE core components read them.

    Called by WhisperFreeApp.__init__ right after ConfigManager is loaded but
    BEFORE HotkeyManager is constructed. Must be cheap and dependency-free
    (no pyobjc, no Qt) so it works even when macOS deps are not yet installed.

    Args:
        config: The ConfigManager instance.
    """
    _apply_macos_hotkey_defaults(config)


def init_macos(app) -> None:
    """Apply macOS-specific runtime initialization.

    Called from platform_init(app) at the end of WhisperFreeApp.__init__,
    after all core/UI components exist.

    Args:
        app: The WhisperFreeApp instance.
    """
    _set_accessory_activation_policy()
    _install_tray_icon(app)


def _set_accessory_activation_policy() -> None:
    """Hide the Dock icon at runtime (parity with LSUIElement=true in the bundled .app).

    The bundled .app uses Info.plist's LSUIElement=true to start as a
    menu-bar agent. But when running from source, the Python interpreter is
    a regular app and shows a Dock icon for "Python" / "python3". This call
    switches the activation policy to Accessory so it disappears live.

    Falls back silently if pyobjc is not installed (pre-Phase-2-deps state).
    """
    try:
        from AppKit import NSApp, NSApplicationActivationPolicyAccessory
        if NSApp is not None:
            NSApp.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
            logger.info("NSApp activation policy set to Accessory (Dock icon hidden)")
        else:
            logger.warning("NSApp is None; cannot set activation policy")
    except ImportError:
        logger.warning(
            "pyobjc not installed; Dock icon will remain visible during dev runs. "
            "Install with: pip install -r requirements-macos.txt"
        )
    except Exception as e:
        logger.warning(f"Could not set activation policy: {e}")


def _install_tray_icon(app) -> None:
    """Construct the menu bar TrayController and wire its signals."""
    from app.platform.macos.tray import TrayController

    icon_path = _find_menu_bar_icon()

    tray = TrayController(icon_path=icon_path, parent=app)

    # Wire signals to the orchestrator. on_hotkey_pressed handles toggle
    # logic via the state machine; main_window.show is idempotent; and
    # request_exit triggers the orderly shutdown path.
    tray.toggle_requested.connect(app.on_hotkey_pressed)
    tray.open_window_requested.connect(_show_main_window_factory(app))
    tray.quit_requested.connect(app.request_exit)

    tray.show()

    # Keep the tray controller alive on the app for the lifetime of the process.
    app.tray = tray
    logger.info("Menu bar tray installed and wired")


def _show_main_window_factory(app):
    """Return a slot that shows + raises + activates the main window.

    On macOS, a hidden Qt window doesn't always come to the front on .show().
    We raise and activate explicitly so the window appears above other apps.
    """
    def _show():
        try:
            app.main_window.show()
            app.main_window.raise_()
            app.main_window.activateWindow()
        except Exception as e:
            logger.error(f"Failed to show main window: {e}")
    return _show


def _apply_macos_hotkey_defaults(config) -> None:
    """If the config has Linux defaults (ctrl+space), upgrade to Mac defaults.

    Right Option is a single-modifier tap-toggle that mirrors macOS native
    Dictation. Cmd+Shift+Space is the fallback (no system conflicts).

    Only writes if the user is still on the cross-platform default
    `ctrl+space` — anything custom is left alone.

    Args:
        config: The ConfigManager instance.
    """
    try:
        primary = config.get('hotkey.primary', 'ctrl+space')
        if primary == 'ctrl+space':
            config.set('hotkey.primary', '<alt_r>')
            logger.info(
                "First-run on macOS: upgraded hotkey.primary from "
                "'ctrl+space' to '<alt_r>' (Right Option)"
            )

        fallback = config.get('hotkey.fallback', 'ctrl+shift+v')
        if fallback == 'ctrl+shift+v':
            config.set('hotkey.fallback', 'cmd+shift+space')
            logger.info(
                "First-run on macOS: upgraded hotkey.fallback from "
                "'ctrl+shift+v' to 'cmd+shift+space'"
            )

        config.save()
    except Exception as e:
        logger.warning(f"Could not apply macOS hotkey defaults: {e}")


def _find_menu_bar_icon() -> Path | None:
    """Locate the menu bar icon asset, if any.

    Looks for `assets/menu-bar-icon.png` first (the designed asset).
    Falls back to None — TrayController will then draw a placeholder.
    """
    here = Path(__file__).resolve()
    # app/platform/macos/init.py -> repo root is parents[3]
    repo_root = here.parents[3]
    candidates = [
        repo_root / 'assets' / 'menu-bar-icon.png',
        repo_root / 'assets' / 'menu-bar-icon@2x.png',
    ]
    for c in candidates:
        if c.exists():
            return c
    return None
