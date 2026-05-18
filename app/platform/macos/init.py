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
    # Honor the user's "Show in Dock" preference (default: False = agent app).
    show_in_dock = False
    try:
        show_in_dock = bool(app.config.get('macos.show_in_dock', False))
    except Exception:
        pass
    set_dock_visible(show_in_dock)

    # Prime macOS TCC for the Mic so PortAudio/sounddevice can actually
    # capture audio. Without this, sounddevice opens a stream successfully
    # but receives a silent zero-fill — TCC doesn't get triggered by
    # PortAudio's CoreAudio path. AVCaptureDevice.requestAccess does the
    # right thing. Safe to call every launch: it's a no-op if already
    # granted and silent (no prompt) for the granted case.
    _prime_microphone_tcc()

    _install_tray_icon(app)


def _prime_microphone_tcc() -> None:
    """Fire AVFoundation Mic request so sounddevice receives real audio.

    Fire-and-forget: the callback runs on a CoreAudio thread and we don't
    wait. Any TCC prompt that shows up is handled by the user; we don't
    block the app startup on it. Subsequent sounddevice InputStream opens
    will then capture real microphone data instead of zeros.
    """
    try:
        from app.platform.macos import hotkey_perms
        hotkey_perms.request_microphone_access(lambda _granted: None)
        logger.debug("AVFoundation Mic TCC primed")
    except Exception as e:
        logger.debug(f"AVFoundation mic priming skipped: {e}")


def apply_overlay_window_behavior(widget) -> bool:
    """Apply macOS-native always-on-top behavior to a Qt widget's NSWindow.

    Configures the underlying NSWindow so the overlay:
      - Appears on every Space (CanJoinAllSpaces).
      - Floats above full-screen apps (FullScreenAuxiliary).
      - Doesn't follow Mission Control / Spaces transitions (Stationary).
      - **Stays visible when our app deactivates** (the default Qt.Tool /
        NSPanel behavior is to auto-hide; we disable it).
      - **Sits above normal app windows** via NSStatusWindowLevel — so the
        overlay is visible while the user is typing into another app.

    Must be called AFTER the widget has been shown at least once — Qt only
    materializes the backing NSView/NSWindow on first show, so winId()
    returns 0 before that.

    Args:
        widget: A QWidget that has already been shown once.

    Returns:
        True on success; False if pyobjc is unavailable, the NSWindow does
        not yet exist, or the call raised.
    """
    try:
        import objc  # type: ignore[import-not-found]
        from AppKit import (  # type: ignore[import-not-found]
            NSWindowCollectionBehaviorCanJoinAllSpaces,
            NSWindowCollectionBehaviorFullScreenAuxiliary,
            NSWindowCollectionBehaviorStationary,
            NSStatusWindowLevel,
        )
    except ImportError:
        logger.warning(
            "pyobjc not installed; overlay will only appear on the current "
            "Space and below full-screen apps. "
            "Install with: pip install -r requirements-macos.txt"
        )
        return False

    try:
        view_ptr = int(widget.winId())
        if view_ptr == 0:
            logger.debug(
                "winId()==0; widget not yet shown — cannot apply NSWindow behavior"
            )
            return False

        # Qt's WId on macOS is an NSView*. Wrap it as a pyobjc object so we
        # can navigate to its NSWindow.
        ns_view = objc.objc_object(c_void_p=view_ptr)
        ns_window = ns_view.window()
        if ns_window is None:
            logger.debug("NSView has no associated NSWindow yet")
            return False

        behavior = (
            NSWindowCollectionBehaviorCanJoinAllSpaces
            | NSWindowCollectionBehaviorFullScreenAuxiliary
            | NSWindowCollectionBehaviorStationary
        )
        ns_window.setCollectionBehavior_(behavior)

        # Keep the panel visible when our app loses focus. Qt.Tool maps to
        # NSPanel and NSPanel.hidesOnDeactivate defaults to YES — that's
        # what makes the overlay disappear when you click into another app.
        try:
            ns_window.setHidesOnDeactivate_(False)
        except Exception as e:
            # setHidesOnDeactivate is an NSPanel selector; if Qt happened
            # to back the widget with a plain NSWindow this will fail —
            # silently fine (NSWindow doesn't auto-hide anyway).
            logger.debug(f"setHidesOnDeactivate_ skipped: {e}")

        # Float above normal app windows so the overlay is visible while
        # the user is typing into another app. NSStatusWindowLevel == 25,
        # which is above NSFloatingWindowLevel (3) and below NSPopUpMenu
        # — about the same level Spotlight and Bartender use.
        ns_window.setLevel_(NSStatusWindowLevel)

        logger.info(
            "Applied NSWindow behavior to overlay: AllSpaces + "
            "FullScreenAuxiliary + Stationary + !hidesOnDeactivate + "
            "StatusWindowLevel"
        )
        return True
    except Exception as e:
        logger.warning(f"Failed to apply overlay NSWindow behavior: {e}")
        return False


def set_dock_visible(visible: bool) -> bool:
    """Show or hide the Dock icon by switching NSApp's activation policy.

    visible=True  -> NSApplicationActivationPolicyRegular  (Dock icon shown)
    visible=False -> NSApplicationActivationPolicyAccessory (Dock icon hidden,
                     matches LSUIElement=true in the bundled .app)

    Returns:
        True on success, False if pyobjc is unavailable or the call failed.
    """
    try:
        from AppKit import (
            NSApp,
            NSApplicationActivationPolicyAccessory,
            NSApplicationActivationPolicyRegular,
        )
    except ImportError:
        logger.warning(
            "pyobjc not installed; cannot toggle Dock visibility. "
            "Install with: pip install -r requirements-macos.txt"
        )
        return False

    try:
        if NSApp is None:
            logger.warning("NSApp is None; cannot set activation policy")
            return False
        policy = (
            NSApplicationActivationPolicyRegular if visible
            else NSApplicationActivationPolicyAccessory
        )
        NSApp.setActivationPolicy_(policy)
        logger.info(
            f"NSApp activation policy set to "
            f"{'Regular (Dock visible)' if visible else 'Accessory (Dock hidden)'}"
        )
        return True
    except Exception as e:
        logger.warning(f"setActivationPolicy failed: {e}")
        return False


# (Previous _set_accessory_activation_policy is now superseded by the
# public set_dock_visible(visible) helper below.)


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
