#!/usr/bin/env python3
"""
Whisper-Free: Main Application Orchestrator

This module integrates all components and manages the application lifecycle:
- Core: WhisperEngine, AudioRecorder, HotkeyManager, StateMachine
- UI: DynamicIslandOverlay, MainWindow
- Data: DatabaseManager, ConfigManager

Workflow:
1. User presses hotkey (CTRL+Space) → Start recording
2. User presses hotkey again → Stop recording & transcribe
3. Transcription complete → Copy to clipboard & show result
4. Auto-return to idle state after 2 seconds
"""

import sys
import logging
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import QApplication, QMessageBox, QProgressDialog
from PySide6.QtCore import QThread, QTimer, Signal, QObject, Qt

# Core components
from app.core.whisper_engine import WhisperEngine
from app.core.audio_capture import AudioRecorder
from app.core.hotkey_manager import HotkeyManager
from app.core.state_machine import StateMachine, ApplicationState
from app.core.transcription_queue_manager import TranscriptionQueueManager
from app.core.ipc_server import IPCServer

# UI components
from app.ui.overlay import DynamicIslandOverlay, OverlayMode
from app.ui.main_window import MainWindow

# Data components
from app.data.database import DatabaseManager
from app.data.config import ConfigManager


# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
    ]
)
logger = logging.getLogger(__name__)


class StartRecordingWorker(QObject):
    """Worker for starting recording in background"""
    finished = Signal()
    error = Signal(str)

    def __init__(self, audio_recorder):
        super().__init__()
        self.audio = audio_recorder

    def start(self):
        try:
            logger.info("Starting audio stream in background...")
            self.audio.start()
            self.finished.emit()
        except Exception as e:
            logger.error(f"Error in StartRecordingWorker: {e}")
            self.error.emit(str(e))

class StopRecordingWorker(QObject):
    """Worker for stopping recording in background"""
    finished = Signal(object)  # Emits audio_data (numpy array)
    error = Signal(str)

    def __init__(self, audio_recorder):
        super().__init__()
        self.audio = audio_recorder

    def stop(self):
        try:
            logger.info("Stopping audio capture in background...")
            audio_data = self.audio.stop()
            self.finished.emit(audio_data)
        except Exception as e:
            logger.error(f"Error in StopRecordingWorker: {e}")
            self.error.emit(str(e))

class TranscriptionWorker(QObject):
    """
    Worker for running Whisper transcription in a background thread.
    Prevents UI freezing during inference.
    """
    finished = Signal(str, str, float)  # text, language, duration
    error = Signal(str)

    def __init__(self, whisper_engine):
        super().__init__()
        self.whisper = whisper_engine

    def transcribe(self, audio_data, language, settings):
        """
        Perform transcription (runs in background thread).
        """
        try:
            # Transcribe
            result = self.whisper.transcribe(
                audio_data,
                language=language,
                **settings
            )

            text = result.get('text', '').strip()
            detected_language = result.get('language', 'unknown')
            duration = result.get('duration', 0.0)

            if not text:
                text = "[No speech detected]"

            self.finished.emit(text, detected_language, duration)

        except Exception as e:
            self.error.emit(str(e))


class ModelLoaderWorker(QObject):
    """Worker for loading Whisper models in background"""
    finished = Signal(str, float)  # model_name, vram_usage
    error = Signal(str)

    def __init__(self, whisper_engine):
        super().__init__()
        self.whisper = whisper_engine

    def load_model(self, model_name: str):
        """Load model in background"""
        try:
            self.whisper.change_model(model_name)
            vram = self.whisper.get_vram_usage()
            self.finished.emit(model_name, vram)
        except Exception as e:
            self.error.emit(str(e))


class WhisperFreeApp(QObject):
    """
    Main application orchestrator.

    Connects all components and manages the complete workflow:
    - Hotkey detection
    - Audio recording
    - Whisper transcription
    - UI updates
    - Clipboard integration
    - History persistence

    Signals:
        start_transcription_signal(object, object, dict)  # Internal signal to trigger worker
        start_stop_recording_signal() # Signal to trigger stop recording worker
    """

    # Signal to start transcription in background
    start_transcription_signal = Signal(object, object, dict)  # audio_data, language, settings
    start_stop_recording_signal = Signal() # Signal to trigger stop recording worker
    start_recording_signal = Signal() # Signal to trigger start recording worker
    start_model_load_signal = Signal(str) # Signal to trigger model loading
    ptt_transcription_complete_signal = Signal(str, str, float)  # text, language, duration (for thread-safe callback)

    def __init__(self):
        super().__init__()

        # Qt Application
        self.app = QApplication.instance()
        if self.app is None:
            self.app = QApplication(sys.argv)

        self.app.setApplicationName("Whisper-Free")
        self.app.setOrganizationName("Whisper-Free")
        self.app.setQuitOnLastWindowClosed(False)
        self._cleanup_done = False
        self._exit_requested = False
        self.app.aboutToQuit.connect(self.cleanup)

        # Configuration directory
        self.config_dir = Path.home() / ".config" / "whisper-free"
        self.config_dir.mkdir(parents=True, exist_ok=True)

        # Initialize data layer
        logger.info("Initializing configuration and database...")
        self.config = ConfigManager(str(self.config_dir / "config.yaml"))
        self.db = DatabaseManager(str(self.config_dir / "history.db"))

        # Initialize core components
        logger.info("Initializing core components...")
        self._init_core_components()

        # Initialize UI components
        logger.info("Initializing UI components...")
        self._init_ui_components()

        # Connect signals
        logger.info("Connecting signals...")
        self._connect_signals()

        # Initialize background workers
        logger.info("Initializing background workers...")
        self._init_workers()

        # IPC server for Wayland hotkey support (whisper --toggle)
        self.ipc_server = IPCServer()
        self.ipc_server.command_received.connect(self._on_ipc_command)

        # Waveform update timer (30 FPS)
        self.waveform_timer = QTimer()
        self.waveform_timer.timeout.connect(self._update_waveform)

        # State tracking
        self.last_transcript = ""
        self.last_audio_data = None

        logger.info("Whisper-Free initialized successfully")

    def _init_core_components(self):
        """Initialize Whisper engine, audio recorder, state machine, hotkey manager"""

        # State machine
        self.state = StateMachine()

        # Whisper engine
        try:
            model_name = self.config.get('whisper.model', 'small')
            device = self.config.get('whisper.device', 'cuda')
            logger.info(f"Loading Whisper model: {model_name} on {device}")

            self.whisper = WhisperEngine(
                model_name=model_name,
                device=device
            )
            logger.info(f"Whisper model loaded. VRAM: {self.whisper.get_vram_usage():.1f} MB")
        except Exception as e:
            logger.error(f"Failed to load Whisper model: {e}")
            QMessageBox.critical(
                None,
                "Whisper Engine Error",
                f"Failed to load Whisper model.\n\n{str(e)}\n\n"
                "Please check that CUDA is available or set device='cpu' in config."
            )
            sys.exit(1)

        # Transcription Queue Manager (prevents KV cache corruption)
        logger.info("Initializing transcription queue manager...")
        self.queue_manager = TranscriptionQueueManager(
            whisper_engine=self.whisper,
            db_manager=self.db
        )
        logger.info("Queue manager initialized")

        # Audio recorder
        try:
            audio_device = self.config.get('audio.device', None)
            self.audio = AudioRecorder(device=audio_device)
            logger.info("Audio recorder initialized")
        except Exception as e:
            logger.error(f"Failed to initialize audio recorder: {e}")
            QMessageBox.critical(
                None,
                "Audio Error",
                f"Failed to initialize audio recorder.\n\n{str(e)}\n\n"
                "Please check your microphone connection."
            )
            sys.exit(1)

        # Hotkey manager (will run in separate thread)
        try:
            hotkey = self.config.get('hotkey.primary', '<ctrl>+<space>')
            self.hotkey = HotkeyManager(hotkey=hotkey)
            self.hotkey_thread = QThread()
            self.hotkey.moveToThread(self.hotkey_thread)
            logger.info(f"Hotkey manager initialized: {hotkey}")
        except Exception as e:
            logger.error(f"Failed to initialize hotkey manager: {e}")
            QMessageBox.critical(
                None,
                "Hotkey Error",
                f"Failed to initialize hotkey manager.\n\n{str(e)}\n\n"
                "Please check your X11 environment."
            )
            sys.exit(1)

    def _init_workers(self):
        """Initialize and start background worker threads"""
        
        # 1. Start Recording Worker
        self.start_recording_worker = StartRecordingWorker(self.audio)
        self.start_recording_thread = QThread()
        self.start_recording_worker.moveToThread(self.start_recording_thread)
        
        self.start_recording_signal.connect(self.start_recording_worker.start)
        self.start_recording_worker.finished.connect(self.on_recording_started)
        self.start_recording_worker.error.connect(self.on_start_recording_error)
        
        self.start_recording_thread.start()

        # 2. Stop Recording Worker
        self.stop_recording_worker = StopRecordingWorker(self.audio)
        self.stop_recording_thread = QThread()
        self.stop_recording_worker.moveToThread(self.stop_recording_thread)
        
        self.start_stop_recording_signal.connect(self.stop_recording_worker.stop)
        self.stop_recording_worker.finished.connect(self.on_recording_stopped)
        self.stop_recording_worker.error.connect(self.on_stop_recording_error)
        
        self.stop_recording_thread.start()

        # 3. Transcription Worker
        self.transcription_worker = TranscriptionWorker(self.whisper)
        self.transcription_thread = QThread()
        self.transcription_worker.moveToThread(self.transcription_thread)
        
        self.start_transcription_signal.connect(self.transcription_worker.transcribe)
        self.transcription_worker.finished.connect(self.on_transcription_complete)
        self.transcription_worker.error.connect(self.on_transcription_error)
        
        self.transcription_thread.start()
        
        # 4. Model Loader Worker
        self.model_loader_worker = ModelLoaderWorker(self.whisper)
        self.model_loader_thread = QThread()
        self.model_loader_worker.moveToThread(self.model_loader_thread)
        
        self.start_model_load_signal.connect(self.model_loader_worker.load_model)
        self.model_loader_worker.finished.connect(self.on_model_loaded)
        self.model_loader_worker.error.connect(self.on_model_load_error)
        
        self.model_loader_thread.start()
        
        logger.info("Background workers initialized and threads started")

    def _init_ui_components(self):
        """Initialize overlay and main window"""

        # Dynamic Island overlay
        self.overlay = DynamicIslandOverlay()
        
        # Apply overlay settings
        position = self.config.get('overlay.position', 'top-center')
        monitor = self.config.get('overlay.monitor', 0)
        self.overlay.set_position(position, monitor)

        auto_dismiss_ms = self.config.get('overlay.auto_dismiss_ms', 1000)
        self.overlay.set_auto_dismiss_ms(auto_dismiss_ms)

        # Main window
        self.main_window = MainWindow(self.db, self.config, self.whisper, self.queue_manager)
        self.main_window.exit_requested.connect(self.request_exit)

        # Update initial VRAM display
        vram_usage = self.whisper.get_vram_usage()
        self.main_window.update_vram_usage(vram_usage)

        self.main_window.update_status("Ready")
        # Update overlay status info
        model_name = self.config.get('whisper.model', 'small')
        device = self.config.get('whisper.device', 'cuda')
        self.overlay.set_status_info(model_name, device, f"{vram_usage:.1f} MB")

    def _connect_signals(self):
        """Wire up all component signals and slots"""

        # Hotkey → Start/Stop recording
        self.hotkey.hotkey_pressed.connect(self.on_hotkey_pressed)

        # State changes → Update UI
        self.state.state_changed.connect(self.on_state_changed)

        # Settings changes → Reload components
        self.main_window.settings_changed.connect(self.on_settings_changed)

        # Settings panel → Model change
        self.main_window.settings_panel.model_changed.connect(self.on_model_changed)

        # History panel → Text copied
        self.main_window.history_panel.text_copied.connect(self.on_text_copied)

        # Overlay Controls
        self.overlay.cancel_requested.connect(self.cancel_recording)
        self.overlay.stop_requested.connect(self.stop_recording)

        # Queue Manager → Job lifecycle
        self.queue_manager.job_started.connect(self._on_job_started)
        self.queue_manager.job_completed.connect(self._on_job_completed)
        self.queue_manager.job_failed.connect(self._on_job_failed)

        # PTT completion signal (thread-safe bridge from worker to main thread)
        self.ptt_transcription_complete_signal.connect(self.on_transcription_complete)

        # PTT button (Wayland-safe UI toggle)
        self.main_window.ptt_toggle_requested.connect(self.on_ptt_button_clicked)

    def on_hotkey_pressed(self):
        """
        Handle hotkey press (CTRL+Space)

        Toggle recording state:
        - IDLE → Start recording
        - RECORDING → Stop recording and transcribe
        - Other states → Ignore (already processing)
        """
        current_state = self.state.current_state
        logger.info(f"Hotkey pressed. Current state: {current_state}")

        if current_state == ApplicationState.IDLE:
            self.start_recording()
        elif current_state == ApplicationState.RECORDING:
            self.stop_recording()
        else:
            logger.info(f"Ignoring hotkey press in state: {current_state}")

    def on_ptt_button_clicked(self):
        """Handle PTT button click (toggle start/stop)."""
        self.on_hotkey_pressed()

    def _on_ipc_command(self, command: str):
        """Handle IPC command from external process (e.g., whisper --toggle)."""
        logger.info(f"IPC command: {command}")
        if command == "toggle":
            self.on_hotkey_pressed()
        else:
            logger.warning(f"Unknown IPC command: {command}")

    def start_recording(self):
        """Begin audio capture (non-blocking)"""
        logger.info("Starting recording process...")

        try:
            # Transition state early to give immediate feedback
            if not self.state.transition_to(ApplicationState.RECORDING):
                logger.error("Failed to transition to RECORDING state")
                return

            # Trigger background worker to start audio stream
            self.start_recording_signal.emit()

        except Exception as e:
            logger.error(f"Failed to start recording: {e}")
            self.state.transition_to(ApplicationState.ERROR, str(e))
            QMessageBox.critical(
                self.main_window,
                "Recording Error",
                f"Failed to start recording.\n\n{str(e)}"
            )

    def on_recording_started(self):
        """Handle successful start of recording stream"""
        logger.info("Recording stream started successfully")
        # Start waveform updates (30 FPS)
        self.waveform_timer.start(33)

    def on_start_recording_error(self, error_message):
        """Handle error during recording start"""
        logger.error(f"Start recording error: {error_message}")
        self.waveform_timer.stop() # Ensure timer is stopped
        self.state.transition_to(ApplicationState.ERROR, error_message)
        QMessageBox.critical(
            self.main_window,
            "Recording Error",
            f"Failed to start recording.\n\n{error_message}"
        )

    def stop_recording(self):
        """Stop capture and start transcription (non-blocking)"""
        logger.info("Stopping recording...")

        try:
            # Stop waveform updates immediately
            self.waveform_timer.stop()

            # Transition to processing immediately to update UI
            # This shows the spinner/processing state while we process the audio
            if not self.state.transition_to(ApplicationState.PROCESSING):
                logger.error("Failed to transition to PROCESSING state")
                return

            # Trigger background worker to stop audio stream and process data
            self.start_stop_recording_signal.emit()

        except Exception as e:
            logger.error(f"Failed to initiate stop recording: {e}")
            self.state.transition_to(ApplicationState.ERROR, str(e))

    def on_recording_stopped(self, audio_data):
        """Handle audio data after recording stops (called from worker)"""
        logger.info(f"Recording stopped, captured {len(audio_data)} samples")

        if len(audio_data) == 0:
            logger.warning("No audio captured")
            self.state.transition_to(ApplicationState.ERROR, "No audio captured")
            QMessageBox.warning(
                self.main_window,
                "No Audio",
                "No audio was captured. Please try again."
            )
            QTimer.singleShot(2000, lambda: self.state.transition_to(ApplicationState.IDLE))
            return

        # Store audio data
        self.last_audio_data = audio_data

        # Submit transcription job to queue manager
        logger.info("Submitting PTT transcription job to queue...")

        # Prepare settings
        language = self.config.get('whisper.language', None)
        settings = {
            'beam_size': self.config.get('whisper.beam_size', 1),
            'temperature': self.config.get('whisper.temperature', 0.0),
            'fp16': self.config.get('whisper.fp16', True)
        }

        # Submit high-priority PTT job (uses queue manager for exclusive model access)
        job_id = self.queue_manager.submit_ptt_job(
            audio_data=self.last_audio_data,
            language=language,
            settings=settings,
            on_complete=self._on_ptt_transcription_complete
        )

        logger.info(f"PTT job {job_id} submitted to queue")

    def _on_ptt_transcription_complete(self, text: str, result_data: dict):
        """
        Callback when PTT transcription completes (called from queue manager worker thread).

        This method is called from the background worker thread, so we must use signals
        to communicate back to the main Qt thread for UI updates.

        Args:
            text: Transcribed text
            result_data: Full Whisper result dictionary
        """
        # Extract metadata from result
        language = result_data.get('language', 'en')

        # Calculate duration from segments if available
        segments = result_data.get('segments', [])
        if segments:
            duration = segments[-1].get('end', 0.0)
        else:
            duration = 0.0

        # Emit signal to main thread (Qt signals are thread-safe)
        # This will trigger on_transcription_complete() in the main thread
        self.ptt_transcription_complete_signal.emit(text, language, duration)

    def on_stop_recording_error(self, error_message):
        """Handle error during stop recording"""
        logger.error(f"Stop recording error: {error_message}")
        self.state.transition_to(ApplicationState.ERROR, error_message)
        QMessageBox.critical(
            self.main_window,
            "Recording Error",
            f"Failed to stop recording.\n\n{error_message}"
        )

    def cancel_recording(self):
        """Cancel the current recording without transcribing."""
        logger.info("Cancelling recording...")
        if self.state.current_state == ApplicationState.RECORDING:
            # Stop updates
            self.waveform_timer.stop()
            
            # Stop audio stream (without processing)
            # We can use the stop worker but ignore the result, 
            # OR just stop the stream directly if possible.
            # Ideally, we should restart the worker or just drain it.
            # For simplicity, let's just trigger a stop but set a flag or handle logic to ignore result.
            # But the cleanest way is often just to invoke stop logic but not transcribe.
            
            # However, since `stop_recording` transitions to PROCESSING,
            # let's manually handle cancellation.
            
            try:
                self.audio.stop() # Just stop stream
            except Exception as e:
                logger.error(f"Error stopping audio on cancel: {e}")
                
            self.state.transition_to(ApplicationState.IDLE)
            logger.info("Recording cancelled")

    def on_transcription_complete(self, text: str, language: str, duration: float):
        """Handle successful transcription"""
        logger.info(f"Handling transcription result: {text[:50]}...")

        try:
            # Copy to clipboard
            self.app.clipboard().setText(text)
            logger.info("Text copied to clipboard")

            # Update main window history
            model_used = self.config.get('whisper.model', 'small')
            self.main_window.add_transcription(text, duration, language, model_used)
            # Note: DB insert moved to main_window.add_transcription to avoid duplicates

            # Show result in overlay
            self.overlay.set_result_text(text, language=language)

            # Transition to completed state
            if not self.state.transition_to(ApplicationState.COMPLETED):
                logger.error("Failed to transition to COMPLETED state")
                return

            # Auto-reset to idle after overlay auto-dismiss completes
            auto_dismiss_ms = self.config.get('overlay.auto_dismiss_ms', 1000)
            QTimer.singleShot(auto_dismiss_ms + 200, self._reset_to_idle)

        except Exception as e:
            logger.error(f"Failed to handle transcription result: {e}")
            self.state.transition_to(ApplicationState.ERROR, str(e))

    def on_transcription_error(self, error_message: str):
        """Handle transcription error"""
        logger.error(f"Transcription error: {error_message}")

        # Transition to error state
        self.state.transition_to(ApplicationState.ERROR, error_message)

        # Show error message
        QMessageBox.critical(
            self.main_window,
            "Transcription Error",
            f"Failed to transcribe audio.\n\n{error_message}"
        )

        # Reset to idle after 2 seconds
        QTimer.singleShot(2000, self._reset_to_idle)

    def _reset_to_idle(self):
        """Reset application to idle state"""
        logger.info("Resetting to idle state")
        self.state.transition_to(ApplicationState.IDLE)

    def on_state_changed(self, new_state: ApplicationState):
        """
        Handle state changes and update UI accordingly

        State mapping to overlay modes:
        - IDLE → MINIMAL
        - RECORDING → LISTENING (with waveform)
        - PROCESSING → PROCESSING (with spinner)
        - COMPLETED → RESULT (with transcript, auto-dismiss)
        - ERROR → MINIMAL (error shown via MessageBox)
        """
        logger.info(f"State changed to: {new_state}")

        # Update status bar
        status_text = {
            ApplicationState.IDLE: "Ready",
            ApplicationState.RECORDING: "Recording",
            ApplicationState.PROCESSING: "Processing",
            ApplicationState.COMPLETED: "Completed",
            ApplicationState.ERROR: "Error"
        }.get(new_state, "Unknown")

        self.main_window.update_status(status_text)
        self.main_window.update_ptt_button(new_state)

        # Update overlay mode
        overlay_mode = {
            ApplicationState.IDLE: OverlayMode.HIDDEN,
            ApplicationState.RECORDING: OverlayMode.LISTENING,
            ApplicationState.PROCESSING: OverlayMode.PROCESSING,
            ApplicationState.COMPLETED: OverlayMode.RESULT,
            ApplicationState.ERROR: OverlayMode.HIDDEN
        }.get(new_state, OverlayMode.HIDDEN)

        self.overlay.set_mode(overlay_mode)

    def _update_waveform(self):
        """Update waveform display during recording (called at 30 FPS)"""
        if self.state.current_state == ApplicationState.RECORDING:
            try:
                levels = self.audio.get_waveform_data()
                if levels:
                    self.overlay.update_waveform(levels)
            except Exception as e:
                logger.error(f"Failed to update waveform: {e}")

    def on_settings_changed(self):
        """Handle settings changes from settings panel"""
        logger.info("Settings changed, reloading configuration...")

        # Reload config (already saved by SettingsPanel)
        # Update components as needed

        # Update hotkey if changed
        new_hotkey = self.config.get('hotkey.primary', '<ctrl>+<space>')
        if self.hotkey.change_hotkey(new_hotkey):
            logger.info(f"Hotkey changed to: {new_hotkey}")
        else:
            logger.error(f"Failed to change hotkey to: {new_hotkey}")

        # Update audio device if changed
        new_device = self.config.get('audio.device', None)
        try:
            self.audio = AudioRecorder(device=new_device)
            logger.info(f"Audio device changed to: {new_device}")
        except Exception as e:
            logger.error(f"Failed to change audio device: {e}")

        # Update overlay settings
        position = self.config.get('overlay.position', 'top-center')
        monitor = self.config.get('overlay.monitor', 0)
        self.overlay.set_position(position, monitor)

        auto_dismiss_ms = self.config.get('overlay.auto_dismiss_ms', 1000)
        self.overlay.set_auto_dismiss_ms(auto_dismiss_ms)

        # Note: Model changes are handled separately via model_changed signal

        logger.info("Settings reloaded successfully")

    def on_model_changed(self, new_model: str):
        """Handle Whisper model change request from settings"""
        logger.info(f"Requesting model change to: {new_model}")

        # Show loading dialog
        self.progress_dialog = QProgressDialog(
            f"Loading Whisper model '{new_model}'...\nThis may take a moment (downloading if needed).",
            None, 0, 0, None
        )
        self.progress_dialog.setWindowTitle("Loading Model")
        self.progress_dialog.setWindowModality(Qt.ApplicationModal)
        self.progress_dialog.setCancelButton(None) # Disable cancel
        self.progress_dialog.setRange(0, 0) # Infinite spinner
        self.progress_dialog.show()
        
        # Trigger background load
        self.start_model_load_signal.emit(new_model)

    def on_model_loaded(self, model_name: str, vram_usage: float):
        """Handle successful model load"""
        logger.info(f"Model '{model_name}' loaded successfully. VRAM: {vram_usage:.1f} MB")
        
        # Close progress dialog
        if hasattr(self, 'progress_dialog'):
            self.progress_dialog.close()
            
        # Update VRAM display
        self.main_window.update_vram_usage(vram_usage)

        # Update status bar


        # Update overlay status info
        device = self.config.get('whisper.device', 'cuda')
        self.overlay.set_status_info(model_name, device, f"{vram_usage:.0f} MB")
        
        QMessageBox.information(
            self.main_window,
            "Model Loaded",
            f"Whisper model '{model_name}' loaded successfully.\n"
            f"VRAM Usage: {vram_usage:.1f} MB"
        )
        
    def on_model_load_error(self, error_msg: str):
        """Handle model load failure"""
        logger.error(f"Failed to load model: {error_msg}")
        
        # Close progress dialog
        if hasattr(self, 'progress_dialog'):
            self.progress_dialog.close()
            
        # Revert config? ideally yes, but for now just warn
        QMessageBox.critical(
            self.main_window,
            "Load Failed",
            f"Failed to load model:\n{error_msg}\n\nFalling back to previous model."
        )

    def on_text_copied(self, text: str):
        """Handle text copied from history panel"""
        logger.info(f"Text copied from history: {text[:50]}...")

        # Show confirmation in overlay
        self.overlay.show_copied_confirmation()

    def _on_job_started(self, job_id: str):
        """Handle queue manager job started signal."""
        logger.debug(f"Job {job_id} started")
        # PTT jobs are already handled by state machine
        # File jobs will be handled by their respective panels

    def _on_job_completed(self, job_id: str, text: str, result_data: dict):
        """Handle queue manager job completed signal."""
        logger.debug(f"Job {job_id} completed")
        # PTT completion is handled via callback
        # File completion is handled by FileTranscribePanel

    def _on_job_failed(self, job_id: str, error_message: str):
        """Handle queue manager job failed signal."""
        logger.error(f"Job {job_id} failed: {error_message}")

        # If this is a PTT job, show error
        if job_id.startswith('ptt_'):
            self.on_transcription_error(error_message)

    def run(self):
        """Start the application"""
        logger.info("Starting Whisper-Free...")

        # Start IPC server (Wayland hotkey support)
        if self.ipc_server.start():
            logger.info("IPC server started (use 'whisper --toggle' for Wayland hotkey)")
        else:
            logger.warning("IPC server failed to start")

        # Start hotkey listener thread
        self.hotkey_thread.started.connect(self.hotkey.start)
        self.hotkey_thread.start()
        logger.info("Hotkey listener started")

        # Show main window
        self.main_window.show()
        logger.info("Main window shown")

        # Show overlay in hidden mode initially (will appear on hotkey)
        if self.config.get('overlay.enabled', True):
            self.overlay.set_mode(OverlayMode.HIDDEN)
            logger.info("Overlay initialized (hidden)")

        # Enter Qt event loop
        logger.info("Entering Qt event loop...")
        exit_code = self.app.exec()

        # Cleanup
        self.cleanup()

        return exit_code

    def cleanup(self):
        """Cleanup resources before exit"""
        if getattr(self, "_cleanup_done", False):
            return
        self._cleanup_done = True

        logger.info("Cleaning up...")

        def _stop_qthread(thread: QThread, name: str):
            if thread and thread.isRunning():
                thread.quit()
                if not thread.wait(2000):
                    logger.warning(f"{name} did not stop in time; terminating")
                    thread.terminate()
                    thread.wait(1000)
                logger.info(f"{name} stopped")

        # Stop IPC server
        if hasattr(self, 'ipc_server'):
            self.ipc_server.stop()

        # Stop hotkey listener
        if self.hotkey_thread.isRunning():
            self.hotkey.stop()
            _stop_qthread(self.hotkey_thread, "Hotkey listener thread")

        # Stop worker thread
        if hasattr(self, 'worker_thread') and self.worker_thread.isRunning():
            self.worker_thread.quit()
            self.worker_thread.wait()
            logger.info("Worker thread stopped")

        # Stop Recording worker thread
        if hasattr(self, 'stop_recording_thread'):
            _stop_qthread(self.stop_recording_thread, "Stop recording thread")

        # Start Recording worker thread
        if hasattr(self, 'start_recording_thread'):
            _stop_qthread(self.start_recording_thread, "Start recording thread")

        # Transcription worker thread
        if hasattr(self, 'transcription_thread'):
            _stop_qthread(self.transcription_thread, "Transcription thread")

        # Model loader thread
        if hasattr(self, 'model_loader_thread'):
            _stop_qthread(self.model_loader_thread, "Model loader thread")

        # Stop queue manager thread
        if hasattr(self, 'queue_manager') and self.queue_manager:
            try:
                self.queue_manager.shutdown()
            except Exception:
                pass

        # Stop audio if recording
        if self.state.current_state == ApplicationState.RECORDING:
            try:
                self.audio.stop()
                logger.info("Audio recording stopped")
            except:
                pass

        # Cleanup Whisper engine (release VRAM)
        try:
            self.whisper.cleanup()
            logger.info("Whisper engine cleaned up")
        except:
            pass

        # Close database
        try:
            self.db.close()
            logger.info("Database closed")
        except:
            pass

        logger.info("Cleanup complete")

    def request_exit(self):
        """Hide UI instantly, then perform shutdown and quit."""
        if self._exit_requested:
            return
        self._exit_requested = True

        # Hide UI immediately for snappy close
        try:
            if self.overlay:
                self.overlay.set_mode(OverlayMode.HIDDEN)
        except Exception:
            pass
        try:
            self.main_window.hide()
        except Exception:
            pass

        # Run cleanup after UI is hidden
        QTimer.singleShot(0, self._finalize_exit)

    def _finalize_exit(self):
        """Perform cleanup and quit the app."""
        self.cleanup()
        self.app.quit()


def main():
    """Main entry point"""
    try:
        app = WhisperFreeApp()
        sys.exit(app.run())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.exception("Fatal error")
        QMessageBox.critical(
            None,
            "Fatal Error",
            f"Whisper-Free encountered a fatal error:\n\n{str(e)}"
        )
        sys.exit(1)


if __name__ == '__main__':
    main()
