"""
AudioRecorder: Real-time microphone audio capture for Whisper transcription.

This module provides efficient audio recording at 16kHz mono (Whisper's native format)
with real-time level monitoring for waveform visualization.

Author: Whisper-Free Project
License: MIT
"""

import sounddevice as sd
import numpy as np
from collections import deque
from typing import List, Optional, Dict, Any
import logging
from scipy import signal
import threading

# Configure logging
logger = logging.getLogger(__name__)


class AudioRecorder:
    """
    Records audio from microphone at 16kHz mono (Whisper native format).
    Provides real-time level data for waveform visualization.

    Uses sounddevice (PortAudio) for cross-platform compatibility.

    Attributes:
        samplerate (int): Sample rate in Hz (always 16000 for Whisper)
        channels (int): Number of channels (always 1 for mono)
        device (int or None): Selected device index
        is_recording (bool): Current recording state

    Example:
        >>> recorder = AudioRecorder()
        >>> recorder.start()
        >>> # ... user speaks ...
        >>> audio = recorder.stop()
        >>> print(f"Captured {len(audio)} samples")
    """

    def __init__(
        self,
        samplerate: int = 16000,
        channels: int = 1,
        device: Optional[int] = None
    ):
        """
        Initialize AudioRecorder.

        Args:
            samplerate: Sample rate in Hz (Whisper requires 16000)
            channels: Number of channels (Whisper requires 1 = mono)
            device: Device index from list_devices() or None for default

        Raises:
            ValueError: If samplerate != 16000 (Whisper requirement)
            RuntimeError: If device is invalid or not available
        """
        # Validate Whisper requirements
        if samplerate != 16000:
            error_msg = (
                f"Whisper requires 16kHz sample rate, got {samplerate}Hz. "
                "This is a hard requirement for accurate transcription."
            )
            logger.error(error_msg)
            raise ValueError(error_msg)

        if channels != 1:
            logger.warning(
                f"Whisper requires mono audio (1 channel), got {channels}. "
                "Forcing channels=1."
            )
            channels = 1

        self.samplerate = samplerate
        self.channels = channels
        self.device = device
        self._stream = None
        self._recording = False
        self._audio_chunks = []
        self._actual_samplerate = samplerate  # May differ from device
        self._lock = threading.Lock()

        # Ring buffer for waveform visualization (last ~1 second)
        # Each chunk is ~20ms, so 50 chunks = 1 second
        self._waveform_buffer = deque(maxlen=50)

        # Validate and query device
        self._validate_device()

        logger.info(
            f"AudioRecorder initialized: {samplerate}Hz mono, "
            f"device={self.device if self.device is not None else 'default'}"
        )

    def _validate_device(self) -> None:
        """
        Validate the selected device exists and supports input.

        Raises:
            RuntimeError: If device is invalid or not available
        """
        try:
            if self.device is not None:
                # Query specific device
                device_info = sd.query_devices(self.device)

                # Check if it's an input device
                if device_info['max_input_channels'] < 1:
                    error_msg = (
                        f"Device {self.device} ('{device_info['name']}') "
                        f"does not support audio input"
                    )
                    logger.error(error_msg)
                    raise RuntimeError(error_msg)

                # Store actual device sample rate
                self._actual_samplerate = int(device_info['default_samplerate'])

                # Warn if device doesn't support 16kHz natively
                if self._actual_samplerate != 16000:
                    logger.warning(
                        f"Device native rate is {self._actual_samplerate}Hz, "
                        f"not 16kHz. Will resample after capture."
                    )

                logger.info(
                    f"Using device: [{self.device}] {device_info['name']} "
                    f"@ {self._actual_samplerate}Hz"
                )
            else:
                # Use default device
                device_info = sd.query_devices(kind='input')
                self._actual_samplerate = int(device_info['default_samplerate'])
                logger.info(
                    f"Using default input device: {device_info['name']} "
                    f"@ {self._actual_samplerate}Hz"
                )

        except Exception as e:
            error_msg = f"Failed to validate audio device: {str(e)}"
            logger.error(error_msg, exc_info=True)
            raise RuntimeError(error_msg) from e

    def _audio_callback(self, indata: np.ndarray, frames: int, time_info, status):
        """
        Audio stream callback (runs in separate thread).

        Args:
            indata: Input audio data (frames x channels)
            frames: Number of frames
            time_info: Time information
            status: Stream status flags
        """
        if status:
            logger.warning(f"Audio stream status: {status}")

        # Copy data (indata is read-only buffer)
        audio_chunk = indata.copy()

        # Convert to mono if needed (though we request 1 channel)
        if audio_chunk.ndim > 1:
            audio_chunk = audio_chunk.mean(axis=1)

        # Flatten to 1D
        audio_chunk = audio_chunk.flatten()

        # Store chunk for later assembly
        with self._lock:
            self._audio_chunks.append(audio_chunk)

        # Calculate RMS level for waveform visualization
        rms_level = np.sqrt(np.mean(audio_chunk**2))

        # Normalize to [0.0, 1.0] range
        # Typical speech is around 0.1-0.3 RMS, so scale accordingly
        normalized_level = min(rms_level * 3.0, 1.0)

        # Add to waveform buffer (thread-safe due to deque)
        self._waveform_buffer.append(float(normalized_level))

    def start(self) -> None:
        """
        Begin recording to internal buffer.
        Clears any previous recording data.

        Raises:
            RuntimeError: If already recording or device unavailable

        Example:
            >>> recorder.start()
            >>> # Recording is now active
        """
        if self._recording:
            error_msg = "Already recording. Call stop() first."
            logger.error(error_msg)
            raise RuntimeError(error_msg)

        # Clear previous data
        with self._lock:
            self._audio_chunks.clear()
        self._waveform_buffer.clear()

        logger.info("Starting audio recording...")

        try:
            # Calculate block size: 20ms at actual device sample rate
            # 20ms = good balance between latency and efficiency
            blocksize = int(self._actual_samplerate * 0.02)  # 20ms

            # Create input stream
            self._stream = sd.InputStream(
                samplerate=self._actual_samplerate,
                channels=self.channels,
                device=self.device,
                dtype=np.float32,  # [-1.0, 1.0] range
                blocksize=blocksize,
                callback=self._audio_callback
            )

            # Start stream
            self._stream.start()
            self._recording = True

            logger.info(
                f"Recording started: {self._actual_samplerate}Hz, "
                f"blocksize={blocksize} ({blocksize/self._actual_samplerate*1000:.1f}ms)"
            )

        except Exception as e:
            error_msg = f"Failed to start recording: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self._recording = False
            if self._stream is not None:
                self._stream.close()
                self._stream = None
            raise RuntimeError(error_msg) from e

    def stop(self) -> np.ndarray:
        """
        Stop recording and return captured audio.

        Returns:
            float32 numpy array, shape (n_samples,) at 16kHz
            Returns empty array if no audio captured

        Note:
            Automatically handles resampling if device capture rate != 16kHz

        Example:
            >>> audio = recorder.stop()
            >>> print(f"Captured {len(audio)/16000:.2f} seconds")
        """
        if not self._recording:
            logger.warning("stop() called but not recording. Returning empty array.")
            return np.array([], dtype=np.float32)

        logger.info("Stopping audio recording...")

        try:
            # Stop and close stream
            if self._stream is not None:
                self._stream.stop()
                self._stream.close()
                self._stream = None

            self._recording = False

            # Assemble audio chunks
            with self._lock:
                if not self._audio_chunks:
                    logger.warning("No audio data captured")
                    return np.array([], dtype=np.float32)

                # Concatenate all chunks
                audio = np.concatenate(self._audio_chunks, axis=0)
                num_chunks = len(self._audio_chunks)
                self._audio_chunks.clear()

            # Ensure float32
            audio = audio.astype(np.float32)

            original_length = len(audio)
            original_duration = original_length / self._actual_samplerate

            logger.info(
                f"Captured {num_chunks} chunks, "
                f"{original_length} samples "
                f"({original_duration:.2f}s at {self._actual_samplerate}Hz)"
            )

            # Resample if needed
            if self._actual_samplerate != self.samplerate:
                logger.info(
                    f"Resampling from {self._actual_samplerate}Hz to {self.samplerate}Hz..."
                )
                audio = self._resample(audio, self._actual_samplerate, self.samplerate)
                resampled_duration = len(audio) / self.samplerate
                logger.info(
                    f"Resampled to {len(audio)} samples ({resampled_duration:.2f}s)"
                )

            return audio

        except Exception as e:
            error_msg = f"Error stopping recording: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self._recording = False
            return np.array([], dtype=np.float32)

    def _resample(
        self,
        audio: np.ndarray,
        orig_sr: int,
        target_sr: int
    ) -> np.ndarray:
        """
        Resample audio from one sample rate to another.

        Args:
            audio: Input audio array
            orig_sr: Original sample rate
            target_sr: Target sample rate

        Returns:
            Resampled audio array
        """
        # Calculate new length
        new_length = int(len(audio) * target_sr / orig_sr)

        # Use scipy's resample (high-quality FFT-based)
        resampled = signal.resample(audio, new_length)

        # Ensure float32
        return resampled.astype(np.float32)

    def get_waveform_data(self) -> List[float]:
        """
        Get recent audio levels for visualization (last ~1 second).
        Values are RMS levels normalized to [0.0, 1.0].

        Returns:
            List of 30-50 float values representing recent audio levels
            Returns empty list if not recording

        Usage:
            Call this from UI thread at 30-60 FPS for smooth waveform animation

        Example:
            >>> while recorder.is_recording():
            >>>     levels = recorder.get_waveform_data()
            >>>     draw_waveform(levels)
            >>>     time.sleep(1/60)  # 60 FPS
        """
        # Convert deque to list (thread-safe read)
        return list(self._waveform_buffer)

    @staticmethod
    def list_devices() -> List[Dict[str, Any]]:
        """
        Enumerate available input devices.

        Returns:
            [
                {
                    'index': 0,
                    'name': 'Built-in Microphone',
                    'channels': 2,
                    'sample_rate': 48000
                },
                ...
            ]

        Example:
            >>> devices = AudioRecorder.list_devices()
            >>> for dev in devices:
            >>>     print(f"[{dev['index']}] {dev['name']}")
        """
        try:
            all_devices = sd.query_devices()
            input_devices = []

            for idx, device in enumerate(all_devices):
                # Only include devices that support input
                if device['max_input_channels'] > 0:
                    input_devices.append({
                        'index': idx,
                        'name': device['name'],
                        'channels': device['max_input_channels'],
                        'sample_rate': int(device['default_samplerate'])
                    })

            logger.debug(f"Found {len(input_devices)} input devices")
            return input_devices

        except Exception as e:
            logger.error(f"Failed to list audio devices: {e}", exc_info=True)
            return []

    def is_recording(self) -> bool:
        """
        Check if currently recording.

        Returns:
            True if recording is active, False otherwise

        Example:
            >>> if recorder.is_recording():
            >>>     print("Recording in progress...")
        """
        return self._recording

    def get_current_duration(self) -> float:
        """
        Get duration of current recording in seconds.

        Returns:
            Duration in seconds (0.0 if not recording or no data)

        Example:
            >>> duration = recorder.get_current_duration()
            >>> print(f"Recording: {duration:.1f}s")
        """
        if not self._recording:
            return 0.0

        with self._lock:
            if not self._audio_chunks:
                return 0.0

            total_samples = sum(len(chunk) for chunk in self._audio_chunks)
            duration = total_samples / self._actual_samplerate
            return duration

    def __repr__(self) -> str:
        """String representation of recorder state."""
        state = "recording" if self._recording else "idle"
        device_str = f"device={self.device}" if self.device is not None else "default device"
        return (
            f"AudioRecorder({state}, {self.samplerate}Hz mono, {device_str})"
        )

    def __del__(self):
        """Destructor to ensure stream is closed."""
        try:
            if hasattr(self, '_stream') and self._stream is not None:
                self._stream.stop()
                self._stream.close()
        except Exception as e:
            logger.debug(f"Error in destructor: {e}")
