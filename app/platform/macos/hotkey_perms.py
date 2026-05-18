"""
macOS permission helpers: Microphone (AVFoundation) + Accessibility (CGEventTap).

These wrap pyobjc framework calls for the onboarding wizard. All functions
degrade gracefully if pyobjc is not installed (returning conservative
"unknown / assume-granted" values and falling back to subprocess shims) so
the wizard never crashes during dev runs without macOS deps.
"""
from __future__ import annotations

import logging
import subprocess
from typing import Callable

logger = logging.getLogger(__name__)


# ---------- Accessibility (pynput global hotkey) ----------

def is_accessibility_granted() -> bool:
    """Return True if this process has Accessibility (AXTrust) permission.

    Uses AXIsProcessTrustedWithOptions so the check does NOT prompt — we
    only want to query state. The system prompt is opaque and unreliable;
    the onboarding wizard surfaces a manual deep-link instead.
    """
    try:
        from ApplicationServices import (
            AXIsProcessTrustedWithOptions,
            kAXTrustedCheckOptionPrompt,
        )
        from CoreFoundation import CFDictionaryCreate, kCFTypeDictionaryKeyCallBacks, kCFTypeDictionaryValueCallBacks

        # Build options dict with prompt=False (we never want the silent prompt).
        options = CFDictionaryCreate(
            None,
            [kAXTrustedCheckOptionPrompt],
            [False],
            1,
            kCFTypeDictionaryKeyCallBacks,
            kCFTypeDictionaryValueCallBacks,
        )
        return bool(AXIsProcessTrustedWithOptions(options))
    except ImportError:
        # Newer pyobjc has a simpler signature exposed.
        try:
            from ApplicationServices import AXIsProcessTrusted
            return bool(AXIsProcessTrusted())
        except ImportError:
            logger.warning(
                "pyobjc-framework-ApplicationServices not installed; "
                "cannot query Accessibility status — assuming granted."
            )
            return True
    except Exception as e:
        logger.warning(f"Accessibility query failed: {e}")
        return True  # Conservative: don't block the user if we can't check


def open_accessibility_settings() -> None:
    """Open System Settings → Privacy & Security → Accessibility."""
    subprocess.run(
        [
            'open',
            'x-apple.systempreferences:com.apple.preference.security'
            '?Privacy_Accessibility',
        ],
        check=False,
    )


# ---------- Microphone (AVFoundation) ----------

def is_microphone_granted() -> bool:
    """Return True if the app has microphone permission.

    Queries AVCaptureDevice.authorizationStatusForMediaType. Does NOT prompt.
    """
    try:
        from AVFoundation import AVCaptureDevice
        # AVMediaTypeAudio constant
        try:
            from AVFoundation import AVMediaTypeAudio
        except ImportError:
            AVMediaTypeAudio = "soun"  # OSType for 'soun'

        # AVAuthorizationStatusAuthorized == 3
        try:
            from AVFoundation import AVAuthorizationStatusAuthorized
        except ImportError:
            AVAuthorizationStatusAuthorized = 3

        status = AVCaptureDevice.authorizationStatusForMediaType_(AVMediaTypeAudio)
        return int(status) == int(AVAuthorizationStatusAuthorized)
    except ImportError:
        logger.warning(
            "pyobjc-framework-AVFoundation not installed; "
            "cannot query Microphone status — assuming granted."
        )
        return True
    except Exception as e:
        logger.warning(f"Microphone query failed: {e}")
        return True


def request_microphone_access(callback: Callable[[bool], None]) -> None:
    """Trigger the system Microphone permission prompt.

    Args:
        callback: Called with True if granted, False if denied. May be
                  invoked on a non-main thread (Cocoa schedules it on a
                  background queue); the caller should marshal to the UI
                  thread via Qt signals if needed.
    """
    try:
        from AVFoundation import AVCaptureDevice
        try:
            from AVFoundation import AVMediaTypeAudio
        except ImportError:
            AVMediaTypeAudio = "soun"

        def _handler(granted):
            try:
                callback(bool(granted))
            except Exception as e:
                logger.error(f"Microphone callback raised: {e}")

        AVCaptureDevice.requestAccessForMediaType_completionHandler_(
            AVMediaTypeAudio,
            _handler,
        )
        return
    except ImportError:
        logger.warning(
            "pyobjc-framework-AVFoundation not installed; "
            "falling back to opening a brief audio stream to trigger the prompt."
        )

    # Fallback: opening a sounddevice InputStream causes macOS to trigger
    # the Microphone permission prompt automatically.
    try:
        import sounddevice as sd
        with sd.InputStream(channels=1, samplerate=16000):
            pass
        callback(True)
    except Exception as e:
        logger.error(f"Microphone fallback request failed: {e}")
        callback(False)
