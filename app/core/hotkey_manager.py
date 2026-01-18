"""
Global Hotkey Manager for Whisper-Free

Handles global hotkey registration and detection on X11.
Runs in separate thread to avoid blocking the UI.

Uses pynput for cross-platform key detection.
"""

from PySide6.QtCore import QObject, Signal
from pynput import keyboard
from typing import Optional
import logging
import os
import threading

logger = logging.getLogger(__name__)


class HotkeyManager(QObject):
    """
    Handles global hotkey registration and detection on X11.
    Runs in separate thread to avoid blocking the UI.

    Uses pynput for cross-platform key detection. For X11-specific needs,
    fallback to python-xlib is possible.

    Signals:
        hotkey_pressed: Emitted when configured hotkey is pressed (toggle behavior)
    """

    hotkey_pressed = Signal()  # Emitted on each hotkey press

    def __init__(self, hotkey: str = "<ctrl>+<space>"):
        """
        Initialize HotkeyManager with specified hotkey.

        Args:
            hotkey: Hotkey string in pynput format
                   Examples: '<ctrl>+<space>', '<ctrl>+<shift>+v', '<alt>+r'

        Note:
            CTRL+Space may conflict with some desktop environments.
            Always provide fallback in settings.

        Raises:
            ValueError: If hotkey format is invalid
        """
        super().__init__()

        self._hotkey = hotkey
        self._listener: Optional[keyboard.GlobalHotKeys] = None
        self._running = False
        self._lock = threading.Lock()

        # Check for X11 environment
        self._check_x11_environment()

        # Validate hotkey format
        try:
            self._hotkey = self._normalize_hotkey(hotkey)
            self._parse_hotkey(self._hotkey)
        except Exception as e:
            raise ValueError(f"Invalid hotkey format '{hotkey}': {e}")

        logger.info(f"HotkeyManager initialized with hotkey: {self._hotkey}")

        logger.info(f"HotkeyManager initialized with hotkey: {hotkey}")

    def _check_x11_environment(self) -> None:
        """
        Check if running on X11 and log warning if not.

        pynput works best on X11. Wayland support is limited.
        """
        session_type = os.environ.get('XDG_SESSION_TYPE', 'unknown')

        if session_type == 'wayland':
            logger.warning(
                "Running on Wayland session. Global hotkeys may not work properly. "
                "Consider switching to X11 session for full functionality."
            )
        elif session_type == 'x11':
            logger.info("Running on X11 session - optimal for global hotkeys")
        else:
            logger.warning(
                f"Unknown session type: {session_type}. "
                "Global hotkeys may not work properly."
            )

    def _parse_hotkey(self, hotkey: str) -> dict:
        """
        Parse and validate hotkey string.

        Args:
            hotkey: Hotkey string in pynput format

        Returns:
            Dictionary mapping hotkey combinations to callbacks

        Raises:
            ValueError: If hotkey format is invalid
        """
        # Parse logic is delegated to pynput after normalization
        # We perform additional validation here
        
        # Validate basic format
        if not hotkey or not isinstance(hotkey, str):
            raise ValueError("Hotkey must be a non-empty string")

        # Check for valid key components
        valid_modifiers = {'<ctrl>', '<alt>', '<shift>', '<cmd>'}
        parts = hotkey.lower().split('+')

        if len(parts) < 1:
            raise ValueError("Hotkey must contain at least one key")

        # Validate format
        for part in parts[:-1]:  # All parts except last should be modifiers
            if part not in valid_modifiers:
                logger.warning(
                    f"Part '{part}' may not be a valid modifier. "
                    f"Valid modifiers: {valid_modifiers}"
                )

        # Create hotkey mapping for pynput
        return {hotkey: self._on_hotkey_activated}

    def _normalize_hotkey(self, hotkey: str) -> str:
        """
        Normalize hotkey string to pynput format.
        
        Converts:
            'ctrl+space' -> '<ctrl>+<space>'
            'alt+shift+r' -> '<alt>+<shift>+r'
        """
        if not hotkey:
            return hotkey
            
        parts = hotkey.lower().split('+')
        normalized_parts = []
        
        # Known modifiers that need brackets
        modifiers = {'ctrl', 'alt', 'shift', 'cmd', 'super'}
        # Keys that also need brackets in pynput
        special_keys = {
            'space', 'enter', 'tab', 'esc', 'backspace', 'delete', 'insert',
            'home', 'end', 'pageup', 'pagedown', 'left', 'right', 'up', 'down',
            'f1', 'f2', 'f3', 'f4', 'f5', 'f6', 'f7', 'f8', 'f9', 'f10', 'f11', 'f12'
        }
        
        for part in parts:
            part = part.strip()
            # If already bracketed, keep it
            if part.startswith('<') and part.endswith('>'):
                normalized_parts.append(part)
                continue
                
            # Wrap modifiers and special keys
            if part in modifiers or part in special_keys:
                normalized_parts.append(f'<{part}>')
            else:
                normalized_parts.append(part)
                
        return '+'.join(normalized_parts)

    def _on_hotkey_activated(self) -> None:
        """
        Internal callback when hotkey is pressed.
        Emits the hotkey_pressed signal.
        """
        logger.debug(f"Hotkey {self._hotkey} activated")
        self.hotkey_pressed.emit()

    def start(self) -> None:
        """
        Start listening for hotkey (blocking call).

        This should be called from a QThread to avoid blocking UI.
        Will run until stop() is called.

        Raises:
            RuntimeError: If hotkey grab fails (e.g., already grabbed by another app)
        """
        with self._lock:
            if self._running:
                logger.warning("HotkeyManager already running")
                return

            try:
                # Parse hotkey and create listener
                hotkey_mapping = self._parse_hotkey(self._hotkey)
                self._listener = keyboard.GlobalHotKeys(hotkey_mapping)

                logger.info(f"Starting hotkey listener for: {self._hotkey}")
                self._running = True

            except Exception as e:
                error_msg = (
                    f"Failed to grab hotkey '{self._hotkey}': {e}. "
                    "It may be already in use by another application."
                )
                logger.error(error_msg)
                raise RuntimeError(error_msg) from e

        # Start listener (blocking call)
        try:
            self._listener.start()
            self._listener.join()  # Block until stopped
        except Exception as e:
            logger.error(f"Error in hotkey listener: {e}")
            with self._lock:
                self._running = False
            raise

    def stop(self) -> None:
        """
        Stop hotkey listener and clean up.
        Safe to call multiple times.
        """
        with self._lock:
            if not self._running:
                logger.debug("HotkeyManager not running, nothing to stop")
                return

            if self._listener is not None:
                try:
                    logger.info("Stopping hotkey listener")
                    self._listener.stop()
                except Exception as e:
                    logger.error(f"Error stopping listener: {e}")
                finally:
                    self._listener = None
                    self._running = False

            logger.info("HotkeyManager stopped")

    def change_hotkey(self, new_hotkey: str) -> bool:
        """
        Change hotkey at runtime without restart.

        Args:
            new_hotkey: New hotkey string in pynput format

        Returns:
            True if successful, False if hotkey invalid or grab failed

        Note:
            This will stop the old listener and start a new one.
            Call from UI thread, it will handle threading internally.
        """
        logger.info(f"Changing hotkey from '{self._hotkey}' to '{new_hotkey}'")

        # Validate new hotkey format
        try:
            new_hotkey = self._normalize_hotkey(new_hotkey)
            self._parse_hotkey(new_hotkey)
        except ValueError as e:
            logger.error(f"Invalid hotkey format: {e}")
            return False

        # Stop current listener if running
        was_running = self.is_running()
        if was_running:
            self.stop()

        # Update hotkey
        old_hotkey = self._hotkey
        self._hotkey = new_hotkey

        # Restart listener if it was running
        if was_running:
            try:
                # Create new listener with new hotkey
                with self._lock:
                    hotkey_mapping = self._parse_hotkey(self._hotkey)
                    self._listener = keyboard.GlobalHotKeys(hotkey_mapping)
                    self._listener.start()
                    self._running = True

                logger.info(f"Successfully changed hotkey to: {new_hotkey}")
                return True

            except Exception as e:
                logger.error(f"Failed to grab new hotkey: {e}")
                # Restore old hotkey
                self._hotkey = old_hotkey
                return False
        else:
            logger.info(f"Hotkey updated to: {new_hotkey} (listener not running)")
            return True

    def is_running(self) -> bool:
        """
        Check if hotkey listener is currently active.

        Returns:
            True if listener is running, False otherwise
        """
        with self._lock:
            return self._running

    def get_current_hotkey(self) -> str:
        """
        Get the current hotkey string.

        Returns:
            Current hotkey configuration
        """
        return self._hotkey

    def __del__(self):
        """Cleanup on deletion"""
        try:
            self.stop()
        except Exception:
            pass
