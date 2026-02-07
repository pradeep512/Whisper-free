"""
TranscriptionQueueManager - Centralized transcription job management

Provides:
- Exclusive Whisper model access (prevents KV cache corruption)
- Priority-based job queue (PTT interrupts file transcription)
- Job status tracking
- Thread-safe operations

This solves the critical "Key and Value sequence length" error that occurs
when multiple threads try to use the Whisper model concurrently.
"""

from enum import Enum, auto
from dataclasses import dataclass, field
from queue import PriorityQueue, Empty
from threading import Lock, Event, Thread
from typing import Optional, Callable
import uuid
import logging
import numpy as np

from PySide6.QtCore import QObject, Signal

logger = logging.getLogger(__name__)


class JobPriority(Enum):
    """Job priority levels (lower value = higher priority)"""
    HIGH = 0    # Push-to-talk (interrupts everything)
    NORMAL = 1  # Single file transcription
    LOW = 2     # Batch transcription


class JobStatus(Enum):
    """Job lifecycle status"""
    PENDING = auto()
    RUNNING = auto()
    PAUSED = auto()
    COMPLETED = auto()
    FAILED = auto()
    CANCELLED = auto()


class JobPausedException(Exception):
    """Raised when a job is paused to allow higher priority jobs to run"""
    pass


@dataclass
class TranscriptionJob:
    """
    Represents a transcription job in the queue.

    Attributes:
        id: Unique job identifier
        priority: Job priority level
        status: Current job status
        audio_data: In-memory audio for PTT jobs
        file_path: File path for file transcription jobs
        language: Language code (or None for auto-detect)
        settings: Whisper transcription settings
        on_progress: Optional progress callback
        on_complete: Optional completion callback
        on_error: Optional error callback
        result_text: Transcription result (populated on completion)
        error_message: Error message (populated on failure)
    """
    id: str
    priority: JobPriority
    status: JobStatus
    audio_data: Optional[np.ndarray] = None
    file_path: Optional[str] = None
    language: Optional[str] = None
    settings: dict = field(default_factory=dict)

    # Callbacks
    on_progress: Optional[Callable] = None
    on_complete: Optional[Callable] = None
    on_error: Optional[Callable] = None

    # Progress tracking (for chunked processing)
    total_chunks: int = 1
    completed_chunks: int = 0
    current_chunk_index: int = 0

    # Results
    result_text: str = ""
    result_data: dict = field(default_factory=dict)
    error_message: str = ""

    def __lt__(self, other):
        """Enable priority queue comparison (lower priority value = higher priority)"""
        return self.priority.value < other.priority.value


class TranscriptionQueueManager(QObject):
    """
    Centralized manager for all transcription jobs.

    Features:
    - Thread-safe exclusive access to Whisper model (prevents KV cache corruption)
    - Priority-based job queue (PTT > single file > batch)
    - Job status tracking
    - Graceful cancellation

    Critical: Only ONE thread can use the Whisper model at a time!
    """

    # Signals for UI updates
    job_started = Signal(str)                # job_id
    job_progress = Signal(str, int)          # job_id, percentage
    job_paused = Signal(str, int)            # job_id, chunk_index
    job_resumed = Signal(str, int)           # job_id, chunk_index
    job_completed = Signal(str, str, dict)   # job_id, text, result_data
    job_failed = Signal(str, str)            # job_id, error_message
    job_cancelled = Signal(str)              # job_id

    def __init__(self, whisper_engine, db_manager=None):
        """
        Initialize queue manager.

        Args:
            whisper_engine: WhisperEngine instance (shared across all jobs)
            db_manager: DatabaseManager instance for job persistence (optional)
        """
        super().__init__()
        self.whisper = whisper_engine
        self.db = db_manager

        # Priority queue for jobs (lower priority number = processed first)
        self.job_queue = PriorityQueue()

        # CRITICAL: Lock for exclusive Whisper model access
        # This prevents concurrent transcription that corrupts KV cache
        self.model_lock = Lock()

        # Currently running job
        self.current_job: Optional[TranscriptionJob] = None
        self.current_job_lock = Lock()

        # Stop event for graceful shutdown
        self.stop_event = Event()

        # Pause event for pausing LOW priority jobs when HIGH priority arrives
        self.pause_event = Event()
        self.pause_event.set()  # Not paused initially

        # Worker thread (processes jobs from queue)
        self.worker_thread = Thread(target=self._process_queue_loop, daemon=True)
        self.worker_thread.start()

        logger.info("TranscriptionQueueManager initialized")

        # Restore pending jobs from database (if available)
        if self.db:
            self._restore_pending_jobs()

    def submit_ptt_job(
        self,
        audio_data: np.ndarray,
        language: Optional[str],
        settings: dict,
        on_complete: Optional[Callable] = None
    ) -> str:
        """
        Submit high-priority push-to-talk transcription job.

        Args:
            audio_data: Audio samples (numpy array)
            language: Language code or None for auto-detect
            settings: Whisper transcription settings
            on_complete: Callback when transcription completes

        Returns:
            Job ID for tracking
        """
        job = TranscriptionJob(
            id=f"ptt_{uuid.uuid4().hex[:8]}",
            priority=JobPriority.HIGH,
            status=JobStatus.PENDING,
            audio_data=audio_data,
            file_path=None,
            language=language,
            settings=settings,
            on_complete=on_complete
        )

        # Add to queue
        self.job_queue.put((job.priority.value, job))

        # Pause any running LOW priority job (file transcription)
        with self.current_job_lock:
            if self.current_job and self.current_job.priority.value > JobPriority.HIGH.value:
                logger.info(f"Pausing LOW priority job {self.current_job.id} for HIGH priority PTT")
                self.pause_event.clear()  # Signal pause

        # Persist to database (if available)
        if self.db:
            try:
                self.db.add_transcription_job(
                    job_id=job.id,
                    priority=job.priority.value,
                    status=job.status.value,
                    file_path=None,
                    language=language,
                    settings=settings
                )
            except Exception as e:
                logger.warning(f"Failed to persist PTT job to database: {e}")

        logger.info(f"Submitted PTT job {job.id} (priority={job.priority.name})")

        return job.id

    def submit_file_job(
        self,
        file_path: str,
        language: Optional[str],
        settings: dict,
        priority: JobPriority = JobPriority.NORMAL,
        on_progress: Optional[Callable] = None,
        on_complete: Optional[Callable] = None
    ) -> str:
        """
        Submit file transcription job.

        Args:
            file_path: Path to audio file
            language: Language code or None for auto-detect
            settings: Whisper transcription settings
            priority: Job priority (NORMAL or LOW for batch)
            on_progress: Optional progress callback
            on_complete: Optional completion callback

        Returns:
            Job ID for tracking
        """
        job = TranscriptionJob(
            id=f"file_{uuid.uuid4().hex[:8]}",
            priority=priority,
            status=JobStatus.PENDING,
            audio_data=None,
            file_path=file_path,
            language=language,
            settings=settings,
            on_progress=on_progress,
            on_complete=on_complete
        )

        # Add to queue
        self.job_queue.put((job.priority.value, job))

        # Persist to database (if available)
        if self.db:
            try:
                self.db.add_transcription_job(
                    job_id=job.id,
                    priority=job.priority.value,
                    status=job.status.value,
                    file_path=file_path,
                    language=language,
                    settings=settings
                )
            except Exception as e:
                logger.warning(f"Failed to persist file job to database: {e}")

        logger.info(f"Submitted file job {job.id} (priority={job.priority.name})")

        return job.id

    def cancel_job(self, job_id: str):
        """
        Cancel a pending or running job.

        Args:
            job_id: ID of job to cancel
        """
        with self.current_job_lock:
            if self.current_job and self.current_job.id == job_id:
                logger.info(f"Cancelling running job {job_id}")
                self.current_job.status = JobStatus.CANCELLED
                self.job_cancelled.emit(job_id)

        # Note: Cannot remove from queue easily, but will be skipped in processing

    def shutdown(self):
        """Gracefully shutdown the queue manager."""
        logger.info("Shutting down TranscriptionQueueManager")
        self.stop_event.set()
        self.worker_thread.join(timeout=5.0)

    def _process_queue_loop(self):
        """
        Background worker loop that processes jobs from the queue.

        CRITICAL: This is the ONLY place where Whisper model is used!
        The model_lock ensures exclusive access.
        """
        logger.info("Queue processing loop started")

        while not self.stop_event.is_set():
            try:
                # Block until a job is available (with timeout for shutdown)
                try:
                    priority_value, job = self.job_queue.get(timeout=1.0)
                except Empty:
                    continue  # Check stop_event and try again

                # Skip cancelled jobs
                if job.status == JobStatus.CANCELLED:
                    logger.info(f"Skipping cancelled job {job.id}")
                    self.job_queue.task_done()
                    continue

                # Set as current job
                with self.current_job_lock:
                    self.current_job = job

                # CRITICAL: Acquire exclusive model access
                # This prevents concurrent transcription that would corrupt KV cache
                with self.model_lock:
                    logger.info(f"Processing job {job.id} (priority={job.priority.name})")
                    self._process_job(job)

                # Clear current job
                with self.current_job_lock:
                    self.current_job = None

                # Resume any paused jobs if this was a HIGH priority job
                if job.priority == JobPriority.HIGH:
                    logger.info("HIGH priority job complete, resuming paused jobs")
                    self.pause_event.set()

                self.job_queue.task_done()

            except Exception as e:
                logger.error(f"Error in queue processing loop: {e}", exc_info=True)
                if job:
                    job.status = JobStatus.FAILED
                    job.error_message = f"Queue error: {str(e)}"
                    self.job_failed.emit(job.id, job.error_message)

        logger.info("Queue processing loop stopped")

    def _process_job(self, job: TranscriptionJob):
        """
        Process a single transcription job.

        Args:
            job: Job to process
        """
        try:
            # Update status to RUNNING
            job.status = JobStatus.RUNNING
            if self.db:
                try:
                    self.db.update_transcription_job(
                        job_id=job.id,
                        status=job.status.value
                    )
                except Exception as e:
                    logger.warning(f"Failed to update job status in database: {e}")

            self.job_started.emit(job.id)

            # Transcribe based on job type
            if job.audio_data is not None:
                # PTT job (in-memory audio)
                result = self._transcribe_audio(job.audio_data, job)
            elif job.file_path is not None:
                # File job (load from disk)
                result = self._transcribe_file(job.file_path, job)
            else:
                raise ValueError("Job has neither audio_data nor file_path")

            # Extract text and metadata
            job.result_text = result.get('text', '')
            job.result_data = result

            # Mark as completed
            if job.status != JobStatus.CANCELLED:
                job.status = JobStatus.COMPLETED

                # Update database
                if self.db:
                    try:
                        self.db.update_transcription_job(
                            job_id=job.id,
                            status=job.status.value,
                            result_text=job.result_text
                        )
                    except Exception as e:
                        logger.warning(f"Failed to update completed job in database: {e}")

                self.job_completed.emit(job.id, job.result_text, job.result_data)
                logger.info(f"Job {job.id} completed ({len(job.result_text)} chars)")

                # Call completion callback if provided
                if job.on_complete:
                    job.on_complete(job.result_text, job.result_data)

        except JobPausedException as e:
            # Job was paused for higher priority work - this is NOT an error
            logger.info(f"Job {job.id} paused: {e}")
            # Job status is already PAUSED and job is already re-queued
            # Just return without marking as failed

        except Exception as e:
            logger.error(f"Job {job.id} failed: {e}", exc_info=True)
            job.status = JobStatus.FAILED
            job.error_message = str(e)

            # Update database
            if self.db:
                try:
                    self.db.update_transcription_job(
                        job_id=job.id,
                        status=job.status.value,
                        error_message=job.error_message
                    )
                except Exception as e:
                    logger.warning(f"Failed to update failed job in database: {e}")

            self.job_failed.emit(job.id, job.error_message)

            # Call error callback if provided
            if job.on_error:
                job.on_error(job.error_message)

    def _transcribe_audio(self, audio: np.ndarray, job: TranscriptionJob) -> dict:
        """
        Transcribe in-memory audio (PTT job).

        Args:
            audio: Audio samples
            job: Job context

        Returns:
            Whisper transcription result
        """
        logger.info(f"Transcribing {len(audio)} audio samples for job {job.id}")

        result = self.whisper.transcribe(
            audio,
            language=job.language,
            **job.settings
        )

        return result

    def _transcribe_file(self, file_path: str, job: TranscriptionJob) -> dict:
        """
        Transcribe audio file with chunked processing and pause/resume support.

        Features:
        - Splits audio into 30-second chunks for checkpointing
        - Checks for pause between chunks (HIGH priority PTT can interrupt)
        - Saves each chunk to database for resume capability
        - Resumes from last checkpoint if interrupted

        Args:
            file_path: Path to audio file
            job: Job context

        Returns:
            Whisper transcription result (combined from all chunks)
        """
        from app.core.audio_file_loader import AudioFileLoader

        logger.info(f"Loading audio file: {file_path}")

        # Load audio
        audio = AudioFileLoader.load_audio(file_path)
        sr = AudioFileLoader.TARGET_SAMPLE_RATE
        audio_duration = len(audio) / 16000  # Duration in seconds

        logger.info(f"Loaded audio: {len(audio)} samples ({audio_duration:.2f}s)")

        # Split into 30-second chunks
        CHUNK_DURATION = 30.0  # seconds
        CHUNK_SIZE = int(CHUNK_DURATION * 16000)  # samples
        chunks = []

        for i in range(0, len(audio), CHUNK_SIZE):
            chunk_audio = audio[i:i + CHUNK_SIZE]
            chunk_start_time = i / 16000
            chunk_end_time = (i + len(chunk_audio)) / 16000
            chunks.append({
                'audio': chunk_audio,
                'start_time': chunk_start_time,
                'end_time': chunk_end_time,
                'index': len(chunks)
            })

        total_chunks = len(chunks)
        logger.info(f"Split audio into {total_chunks} chunks of ~{CHUNK_DURATION}s each")

        # Check for existing chunks (resume from checkpoint)
        existing_chunks = []
        start_chunk_index = job.current_chunk_index  # Resume from where we paused

        # If resuming from database (not from pause), use saved chunks
        if start_chunk_index == 0 and self.db:
            try:
                existing_chunks = self.db.get_job_chunks(job.id)
                if existing_chunks:
                    start_chunk_index = len(existing_chunks)
                    logger.info(f"Resuming from database chunk {start_chunk_index}/{total_chunks}")
            except Exception as e:
                logger.warning(f"Failed to get existing chunks: {e}")
        elif start_chunk_index > 0:
            logger.info(f"Resuming from paused chunk {start_chunk_index}/{total_chunks}")

        # Transcribe chunks
        all_segments = []
        all_text_parts = []

        for chunk_idx in range(start_chunk_index, total_chunks):
            chunk = chunks[chunk_idx]

            # Check if paused (HIGH priority job arrived)
            if not self.pause_event.wait(timeout=0.1):
                logger.info(f"Job {job.id} paused at chunk {chunk_idx}/{total_chunks}")

                # Update job status to PAUSED
                job.status = JobStatus.PAUSED
                if self.db:
                    try:
                        self.db.update_transcription_job(
                            job_id=job.id,
                            status=job.status.value,
                            current_chunk_index=chunk_idx
                        )
                    except Exception as e:
                        logger.warning(f"Failed to update paused job: {e}")

                # Emit paused signal
                self.job_paused.emit(job.id, chunk_idx)

                # Re-queue job to resume later (after HIGH priority job completes)
                logger.info(f"Re-queueing paused job {job.id} to resume at chunk {chunk_idx}")
                self.job_queue.put((job.priority.value, job))

                # Raise special exception to exit transcription and release model_lock
                # This allows HIGH priority job to acquire the lock immediately
                raise JobPausedException(f"Job {job.id} paused for higher priority job")

            # Check if cancelled
            if job.status == JobStatus.CANCELLED:
                logger.info(f"Job {job.id} cancelled at chunk {chunk_idx}/{total_chunks}")
                raise RuntimeError("Job cancelled")

            # Transcribe this chunk
            logger.debug(f"Transcribing chunk {chunk_idx + 1}/{total_chunks}")

            chunk_result = self.whisper.transcribe(
                chunk['audio'],
                language=job.language,
                **job.settings
            )

            chunk_text = chunk_result.get('text', '').strip()
            chunk_segments = chunk_result.get('segments', [])

            # Adjust segment timestamps to absolute time
            for segment in chunk_segments:
                segment['start'] += chunk['start_time']
                segment['end'] += chunk['start_time']

            all_segments.extend(chunk_segments)
            all_text_parts.append(chunk_text)

            # Save chunk to database
            if self.db:
                try:
                    self.db.add_transcription_chunk(
                        job_id=job.id,
                        chunk_index=chunk_idx,
                        text=chunk_text,
                        start_time=chunk['start_time'],
                        end_time=chunk['end_time']
                    )
                except Exception as e:
                    logger.warning(f"Failed to save chunk {chunk_idx}: {e}")

            # Update progress
            progress = int((chunk_idx + 1) / total_chunks * 100)
            if self.db:
                try:
                    self.db.update_transcription_job(
                        job_id=job.id,
                        completed_chunks=chunk_idx + 1,
                        current_chunk_index=chunk_idx + 1
                    )
                except Exception as e:
                    logger.warning(f"Failed to update progress: {e}")

            # Emit progress signal
            self.job_progress.emit(job.id, progress)
            if job.on_progress:
                job.on_progress(progress)

            logger.debug(f"Completed chunk {chunk_idx + 1}/{total_chunks} ({progress}%)")

        # Combine all text parts
        combined_text = ' '.join(all_text_parts)

        # Create combined result
        result = {
            'text': combined_text,
            'segments': all_segments,
            'language': job.language or 'en'
        }

        logger.info(f"File transcription complete: {len(combined_text)} chars, {len(all_segments)} segments")

        return result

    def submit_batch_jobs(self, file_paths: list, language: Optional[str], settings: dict) -> list:
        """
        Submit multiple file transcription jobs as a batch (LOW priority).

        Args:
            file_paths: List of audio file paths
            language: Language code or None for auto-detect
            settings: Whisper transcription settings

        Returns:
            List of job IDs
        """
        job_ids = []
        for file_path in file_paths:
            job_id = self.submit_file_job(
                file_path=file_path,
                language=language,
                settings=settings,
                priority=JobPriority.LOW
            )
            job_ids.append(job_id)

        logger.info(f"Submitted batch of {len(job_ids)} file jobs")
        return job_ids

    def retry_job(self, job_id: str):
        """
        Retry a failed job.

        Args:
            job_id: Job ID to retry
        """
        if not self.db:
            logger.warning("Cannot retry job: no database manager available")
            return

        try:
            # Get job from database
            job_data = self.db.get_transcription_job(job_id)
            if not job_data:
                logger.error(f"Job {job_id} not found in database")
                return

            if job_data['status'] != JobStatus.FAILED.value:
                logger.warning(f"Job {job_id} is not in FAILED state (status={job_data['status']})")
                return

            # Reset job status
            self.db.update_transcription_job(
                job_id=job_id,
                status=JobStatus.PENDING.value,
                current_chunk_index=0,
                error_message=""
            )

            # Re-submit to queue
            self.submit_file_job(
                file_path=job_data['file_path'],
                language=job_data['language'],
                settings=job_data['settings'],
                priority=JobPriority(job_data['priority'])
            )

            logger.info(f"Retrying job {job_id}")

        except Exception as e:
            logger.error(f"Failed to retry job {job_id}: {e}")

    def _restore_pending_jobs(self):
        """
        Restore pending/paused jobs from database on startup.
        """
        try:
            pending_jobs = self.db.get_pending_jobs()
            if not pending_jobs:
                logger.info("No pending jobs to restore")
                return

            logger.info(f"Restoring {len(pending_jobs)} pending jobs")

            for job_data in pending_jobs:
                # Only restore file jobs (PTT jobs are in-memory only)
                if not job_data.get('file_path'):
                    continue

                # Re-submit to queue
                self.submit_file_job(
                    file_path=job_data['file_path'],
                    language=job_data['language'],
                    settings=job_data['settings'],
                    priority=JobPriority(job_data['priority'])
                )

                logger.info(f"Restored job {job_data['id']}")

        except Exception as e:
            logger.error(f"Failed to restore pending jobs: {e}")
