"""
Application State Machine for Whisper-Free

Manages application state transitions with validation.
Provides thread-safe state management for the transcription workflow.
"""

from enum import Enum
from PySide6.QtCore import QObject, Signal
from typing import Optional, Set
import logging
import threading

logger = logging.getLogger(__name__)


class ApplicationState(Enum):
    """
    Application states for the transcription workflow.

    State Flow:
        IDLE → RECORDING → PROCESSING → COMPLETED → IDLE
        Any state → ERROR → IDLE (error recovery)
    """
    IDLE = "idle"           # Ready for new recording
    RECORDING = "recording"  # Currently capturing audio
    PROCESSING = "processing"  # Transcribing audio
    COMPLETED = "completed"   # Transcript ready (transient state)
    ERROR = "error"          # Error occurred


class StateMachine(QObject):
    """
    Manages application state transitions with validation.
    Emits signals for UI updates.

    Thread-safe for concurrent state queries and transitions.

    Signals:
        state_changed(ApplicationState): Emitted after successful state change
        error_occurred(str): Emitted when entering ERROR state with error message
    """

    state_changed = Signal(ApplicationState)
    error_occurred = Signal(str)  # Error message

    # Valid state transitions
    VALID_TRANSITIONS = {
        ApplicationState.IDLE: {
            ApplicationState.RECORDING,
            ApplicationState.ERROR
        },
        ApplicationState.RECORDING: {
            ApplicationState.PROCESSING,
            ApplicationState.IDLE,  # Cancel recording
            ApplicationState.ERROR
        },
        ApplicationState.PROCESSING: {
            ApplicationState.COMPLETED,
            ApplicationState.ERROR
        },
        ApplicationState.COMPLETED: {
            ApplicationState.IDLE,
            ApplicationState.ERROR
        },
        ApplicationState.ERROR: {
            ApplicationState.IDLE  # Recovery
        }
    }

    def __init__(self):
        """Initialize state machine in IDLE state"""
        super().__init__()

        self._current_state = ApplicationState.IDLE
        self._lock = threading.RLock()

        logger.info("StateMachine initialized in IDLE state")

    def transition_to(
        self,
        new_state: ApplicationState,
        error_message: Optional[str] = None
    ) -> bool:
        """
        Attempt state transition with validation.

        Args:
            new_state: Target state
            error_message: Required if transitioning to ERROR state

        Returns:
            True if transition successful, False if invalid

        Side Effects:
            - Emits state_changed signal on success
            - Emits error_occurred signal if transitioning to ERROR
            - Logs state transitions

        Note:
            This method is thread-safe.

        Raises:
            ValueError: If transitioning to ERROR without error_message
        """
        # Validate ERROR state requirements
        if new_state == ApplicationState.ERROR and not error_message:
            raise ValueError("error_message is required when transitioning to ERROR state")

        with self._lock:
            old_state = self._current_state

            # Check if transition is valid
            if not self.can_transition_to(new_state):
                logger.warning(
                    f"Invalid transition: {old_state.value} → {new_state.value}"
                )
                return False

            # Perform transition
            self._current_state = new_state
            logger.info(f"State: {old_state.value} → {new_state.value}")

        # Emit signals (outside lock to avoid deadlock)
        self.state_changed.emit(new_state)

        if new_state == ApplicationState.ERROR:
            logger.error(f"Entered ERROR state: {error_message}")
            self.error_occurred.emit(error_message)

        return True

    def can_transition_to(self, new_state: ApplicationState) -> bool:
        """
        Check if transition to new_state is allowed from current state.

        Args:
            new_state: State to check

        Returns:
            True if transition is valid

        Transition Rules:
            IDLE → RECORDING
            RECORDING → PROCESSING, IDLE (cancel)
            PROCESSING → COMPLETED, ERROR
            COMPLETED → IDLE
            ERROR → IDLE
            Any → ERROR (always allowed)

        Note:
            This method does NOT require the lock because it only reads
            the current state and VALID_TRANSITIONS (which is immutable).
            However, for absolute thread safety, we still use the lock.
        """
        with self._lock:
            current = self._current_state

        # ERROR state can always be reached from any state
        if new_state == ApplicationState.ERROR:
            return True

        # Check valid transitions
        return new_state in self.VALID_TRANSITIONS.get(current, set())

    @property
    def current_state(self) -> ApplicationState:
        """
        Get current state (thread-safe).

        Returns:
            Current application state
        """
        with self._lock:
            return self._current_state

    def reset(self) -> None:
        """
        Force reset to IDLE state (for error recovery).

        This is an emergency recovery method that bypasses
        normal transition validation.

        Side Effects:
            - Emits state_changed signal
            - Logs the reset operation
        """
        with self._lock:
            old_state = self._current_state
            self._current_state = ApplicationState.IDLE
            logger.warning(f"Force reset: {old_state.value} → IDLE")

        # Emit signal outside lock
        self.state_changed.emit(ApplicationState.IDLE)

    def is_busy(self) -> bool:
        """
        Check if state machine is in a working state.

        Returns:
            True if RECORDING or PROCESSING, False otherwise
        """
        with self._lock:
            return self._current_state in {
                ApplicationState.RECORDING,
                ApplicationState.PROCESSING
            }

    def get_state_name(self) -> str:
        """
        Get human-readable name of current state.

        Returns:
            State name as string
        """
        with self._lock:
            return self._current_state.value

    def __repr__(self) -> str:
        """String representation of state machine"""
        return f"StateMachine(current_state={self.current_state.value})"

    def __str__(self) -> str:
        """Human-readable string representation"""
        return f"State: {self.current_state.value}"
