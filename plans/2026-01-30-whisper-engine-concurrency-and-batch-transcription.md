# Comprehensive Implementation Plan: Fix Whisper Engine Concurrency & Add Batch Transcription

**Created**: 2026-01-30
**Status**: Planning
**Priority**: Critical

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Current Issues Analysis](#current-issues-analysis)
3. [Root Cause Analysis](#root-cause-analysis)
4. [Proposed Architecture Changes](#proposed-architecture-changes)
5. [Implementation Plan](#implementation-plan)
6. [Testing Strategy](#testing-strategy)
7. [Migration & Rollback](#migration--rollback)

---

## Executive Summary

### Problems Identified

1. **CRITICAL: KV Cache Corruption** - WhisperEngine's attention cache gets corrupted when push-to-talk and file transcription run concurrently, causing:
   - `RuntimeError: Key and Value must have the same sequence length`
   - Gibberish transcriptions
   - Application crashes

2. **History Panel Glitches** - Windows appearing/disappearing after file transcription due to:
   - Multiple rapid history reloads
   - Incorrect source_type in database entries
   - UI update race conditions

3. **No Concurrent Transcription Support** - Users cannot use push-to-talk while file transcription is in progress

4. **Limited File Transcription** - Only single file processing, no batch operations, no error recovery

### Proposed Solution

Implement a **Transcription Queue Manager** with:
- **Exclusive Model Access Control**: Lock-based serialization of Whisper model usage
- **Priority Queue System**: Push-to-talk interrupts file transcription with pause/resume
- **Batch Processing**: Multiple file transcription with individual error handling
- **Enhanced UI Feedback**: Progress tracking, error indicators, retry mechanisms
- **Database Schema Updates**: Proper job tracking and status management

### Success Criteria

- ✅ Push-to-talk works reliably during file transcription
- ✅ File transcription pauses and resumes without corruption
- ✅ Batch transcription processes multiple files sequentially
- ✅ UI clearly shows status of all transcription jobs
- ✅ Failed jobs can be retried individually
- ✅ No KV cache corruption errors
- ✅ History panel updates smoothly without glitches

---

## Current Issues Analysis

### Issue 1: KV Cache Corruption ⚠️⚠️⚠️

**Error Message**:
```
RuntimeError: Key and Value must have the same sequence length
```

**Error Location**:
```
app/core/whisper_engine.py:198 -> model.transcribe()
  └─> whisper/model.py:124 -> qkv_attention()
      └─> scaled_dot_product_attention(q, k, v)
```

**Occurrence Pattern**:
```
Timeline of Issue:
11:49:40 - File transcription starts (Docker video, 2352s)
11:49:56 - User presses Ctrl+Space (starts PTT recording)
11:49:57 - User stops PTT recording (triggers transcription)
11:49:57 - ERROR: Key and Value must have the same sequence length
```

**Root Cause**:
- Single WhisperEngine instance shared between:
  - `TranscriptionWorker` (push-to-talk) in `transcription_thread`
  - `FileTranscriptionWorker` in ephemeral file transcription threads
- Both workers call `whisper_engine.transcribe()` concurrently
- Whisper's decoder maintains **KV cache** (key-value attention cache) as internal state
- Concurrent calls corrupt this cache:
  ```
  Thread 1 (File):  q=[1500], k=[1500], v=[1500] (39 min audio)
  Thread 2 (PTT):   q=[134],  k=[134],  v=[134]  (1.34s audio)

  Collision! Thread 2 overwrites Thread 1's KV cache mid-decode
  Thread 1 resumes: expects k=[1500], but finds k=[134]
  → RuntimeError: sequence length mismatch
  ```

**Evidence from Logs**:
```
7%|██▏  | 17154/235187 [00:13<02:57]  ← File transcription at 7%
  0%|     | 0/134 [00:00<?, ?frames/s]  ← PTT starts transcription
ERROR: Key and Value must have the same sequence length
```

**Current Mitigation**: None (relies on user not triggering both simultaneously)

---

### Issue 2: History Panel Windows Glitching

**Symptom**: After file transcription completes, pushing to talk causes windows to briefly appear and disappear

**Error Pattern**:
```
11:53:59 - File transcription complete
11:53:59 - Added transcription ID 534 (source=microphone) ← WRONG! Should be 'file'
11:53:59 - Loaded 2 transcriptions (HistoryPanel reload)
11:54:08 - User starts PTT
11:54:26 - PTT complete
11:54:26 - Added transcription ID 535 (source=microphone) ← Correct
11:54:26 - Loaded 3 transcriptions (HistoryPanel reload)
```

**Root Cause Analysis**:

1. **Incorrect Database Source Type**:
   ```python
   # app/core/file_transcription_worker.py:224
   db.add_transcription(
       text=text,
       language=result.get('language'),
       duration=duration,
       model_used=self.whisper_engine.current_model,
       audio_path=self.file_path,
       source_type='microphone'  # ← BUG! Should be 'file'
   )
   ```

2. **Multiple Rapid History Reloads**:
   ```python
   # Signal chain causes multiple reloads:
   FileTranscribePanel.transcription_complete
     └─> add_to_history (manual DB insert)
         └─> db.add_transcription()
             └─> file_transcription_completed signal
                 └─> main_window.on_file_transcription_completed()
                     └─> history_panel.load_history()  # Reload 1
                         └─> HistoryPanel emits history_updated
                             └─> (potentially triggers another reload)
   ```

3. **Window Geometry Thrashing**:
   - HistoryPanel uses `QScrollArea` with dynamic content
   - Each reload triggers `sizeHint()` recalculation
   - Causes brief window resize/redraw
   - On some window managers, this manifests as visible "flashing"

---

### Issue 3: No Pause/Resume Support

**Current Behavior**:
- File transcription is atomic (all-or-nothing)
- `FileTranscriptionWorker.run()` processes entire audio file
- No checkpointing or state persistence
- If interrupted, entire transcription is lost

**User Pain Point**:
```
Scenario: User transcribes a 40-minute video
- 15 minutes in, user needs to dictate a quick note via PTT
- Options:
  a) Wait 25 more minutes for file transcription to finish
  b) Cancel file transcription (loses all progress)
  c) Try PTT anyway (triggers KV cache error)
```

**Required Architecture**:
- Chunk-based processing with state persistence
- Pause mechanism that saves progress
- Resume mechanism that continues from checkpoint
- Priority queue for managing PTT interruptions

---

### Issue 4: No Batch Transcription

**Current Limitation**:
```python
# app/ui/file_transcribe_panel.py:_on_browse_clicked()
file_path, _ = QFileDialog.getOpenFileName(...)  # Single file only
```

**User Request**:
- Select multiple audio files (e.g., 10 podcast episodes)
- Transcribe them sequentially (one-by-one)
- If one fails, show error indicator and continue with next
- Allow retrying failed files without re-selecting all files
- Pause entire batch if PTT is triggered

**Required UI Changes**:
- File list table (not single file display)
- Per-file status indicators (pending, processing, completed, failed)
- Batch progress bar (e.g., "File 3 of 10")
- Individual file retry buttons
- Pause/Resume batch controls

---

## Root Cause Analysis

### Architectural Deficiencies

#### 1. Shared Mutable State in WhisperEngine

**Problem**: Single model instance with internal state shared across threads

```python
# Current architecture (UNSAFE):
class WhisperEngine:
    def __init__(self):
        self.model = whisper.load_model(...)  # Has internal KV cache

    def transcribe(self, audio):
        return self.model.transcribe(audio)  # NOT THREAD-SAFE!

# Used by:
TranscriptionWorker (Thread 1)          ─┐
FileTranscriptionWorker (Thread 2)      ─┼─> Same model instance
ModelLoaderWorker (Thread 3)            ─┘
```

**Why It's Unsafe**:
- Whisper's `model.decode()` maintains KV cache across decode steps
- Cache stores intermediate attention key-value pairs
- Concurrent calls overwrite each other's cache entries
- No locking mechanism in OpenAI Whisper library

**Manifestation**:
```
Frame 1 (File):  K=[batch, heads, seq_len=1500, dim]
Frame 1 (PTT):   K=[batch, heads, seq_len=134, dim]  ← Overwrites!
Frame 2 (File):  Q=[..., seq_len=1500, ...]
                 K=[..., seq_len=134, ...]  ← Mismatch!

torch.scaled_dot_product_attention(Q, K, V)
  → RuntimeError: sequence length must match
```

#### 2. No Transcription Job Management

**Problem**: Ad-hoc worker creation without centralized orchestration

```python
# Push-to-Talk (main.py):
self.transcription_worker = TranscriptionWorker(...)
self.transcription_thread.start()

# File Transcription (file_transcribe_panel.py):
worker = FileTranscriptionWorker(...)
thread = QThread()
worker.moveToThread(thread)
thread.start()

# Result: No coordination, no priorities, no queuing
```

**Missing Capabilities**:
- Job priority (PTT should interrupt file transcription)
- Job queuing (batch transcriptions)
- Job lifecycle (pause, resume, cancel, retry)
- Job status tracking (pending, running, paused, completed, failed)

#### 3. Atomic File Processing

**Problem**: File transcription is all-or-nothing

```python
# Current workflow in FileTranscriptionWorker.run():
audio = load_entire_file()          # Load all 40 minutes
result = transcribe(audio)          # Transcribe all 40 minutes
save_result()                       # Save all
```

**Why It's a Problem**:
- No checkpointing (lose all progress on interruption)
- No incremental results (can't see partial transcription)
- Memory intensive (entire audio in RAM)
- Long uninterruptible operations

**Required Design**:
```python
# Chunked workflow with checkpointing:
for chunk in split_audio_into_30s_chunks(audio):
    if pause_requested:
        save_checkpoint(current_chunk_index, partial_results)
        break

    chunk_result = transcribe(chunk)
    partial_results.append(chunk_result)
    emit_progress(chunk_index / total_chunks)
```

---

## Proposed Architecture Changes

### Overview Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Whisper-Free Application                         │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  ┌──────────────┐         ┌────────────────────────────────┐        │
│  │   PTT Input  │────────>│  Transcription Queue Manager   │        │
│  │ (Ctrl+Space) │  HIGH   │                                │        │
│  └──────────────┘  PRIO   │  - Job Priority Queue          │        │
│                            │  - Whisper Model Lock          │        │
│  ┌──────────────┐         │  - Pause/Resume Controller     │        │
│  │  File Panel  │────────>│  - Batch Job Coordinator       │        │
│  │ (Select Files│  LOW    │                                │        │
│  └──────────────┘  PRIO   └────────┬───────────────────────┘        │
│                                     │                                │
│                                     │ Serialized Access              │
│                                     v                                │
│                        ┌────────────────────────┐                    │
│                        │   WhisperEngine        │                    │
│                        │   + Model Lock         │                    │
│                        │   + KV Cache (safe)    │                    │
│                        └────────────────────────┘                    │
│                                     │                                │
│                                     │ Results                        │
│                                     v                                │
│  ┌──────────────────────────────────────────────────────┐            │
│  │          Enhanced Database Schema                    │            │
│  │  - transcriptions (existing)                         │            │
│  │  - transcription_jobs (NEW)                          │            │
│  │    - id, status, priority, file_path, progress       │            │
│  │    - chunk_index, checkpoint_data, error_message     │            │
│  │  - transcription_chunks (NEW)                        │            │
│  │    - job_id, chunk_index, text, start_time, end_time │            │
│  └──────────────────────────────────────────────────────┘            │
│                                                                       │
│  ┌──────────────────────────────────────────────────────┐            │
│  │          Enhanced UI Components                       │            │
│  │  - BatchTranscriptionPanel (NEW)                     │            │
│  │    - File list table with status icons               │            │
│  │    - Per-file progress bars                          │            │
│  │    - Retry/Cancel buttons                            │            │
│  │  - StatusIndicatorWidget (NEW)                       │            │
│  │    - Shows active/paused/failed states               │            │
│  │  - HistoryPanel (UPDATED)                            │            │
│  │    - Debounced updates to prevent flashing           │            │
│  │    - Correct source_type filtering                   │            │
│  └──────────────────────────────────────────────────────┘            │
└─────────────────────────────────────────────────────────────────────┘
```

---

### Component 1: Transcription Queue Manager

**Location**: `app/core/transcription_queue_manager.py` (NEW)

**Responsibilities**:
1. **Job Submission**: Accept transcription requests from PTT and file panel
2. **Priority Scheduling**: PTT jobs interrupt file jobs
3. **Model Access Control**: Serialize access to WhisperEngine via lock
4. **Pause/Resume**: Checkpoint file transcription state when PTT arrives
5. **Batch Coordination**: Process multiple files sequentially
6. **Error Handling**: Retry failed jobs, log errors

**API Design**:

```python
from enum import Enum, auto
from dataclasses import dataclass
from queue import PriorityQueue
from threading import Lock, Event
from typing import Optional, Callable

class JobPriority(Enum):
    HIGH = 0    # Push-to-talk (interrupts everything)
    NORMAL = 1  # Single file transcription
    LOW = 2     # Batch transcription

class JobStatus(Enum):
    PENDING = auto()
    RUNNING = auto()
    PAUSED = auto()
    COMPLETED = auto()
    FAILED = auto()
    CANCELLED = auto()

@dataclass
class TranscriptionJob:
    id: str
    priority: JobPriority
    status: JobStatus
    audio_data: Optional[np.ndarray]  # For PTT (in-memory)
    file_path: Optional[str]          # For file transcription
    language: str
    settings: dict

    # Progress tracking
    total_chunks: int = 1
    completed_chunks: int = 0
    current_chunk_index: int = 0

    # Results
    result_text: str = ""
    error_message: str = ""

    # Callbacks
    on_progress: Optional[Callable] = None
    on_complete: Optional[Callable] = None
    on_error: Optional[Callable] = None

class TranscriptionQueueManager(QObject):
    """
    Centralized manager for all transcription jobs.

    Features:
    - Priority queue (PTT > single file > batch)
    - Pause/resume file transcriptions when PTT arrives
    - Thread-safe Whisper model access
    - Job status tracking and persistence
    """

    # Signals
    job_started = Signal(str)            # job_id
    job_progress = Signal(str, int)      # job_id, percentage
    job_paused = Signal(str)             # job_id
    job_resumed = Signal(str)            # job_id
    job_completed = Signal(str, str)     # job_id, result_text
    job_failed = Signal(str, str)        # job_id, error_message

    def __init__(self, whisper_engine: WhisperEngine, db: DatabaseManager):
        super().__init__()
        self.whisper = whisper_engine
        self.db = db

        # Thread-safe job queue (priority-based)
        self.job_queue: PriorityQueue[tuple[int, TranscriptionJob]] = PriorityQueue()

        # Lock for exclusive Whisper model access
        self.model_lock = Lock()

        # Currently running job
        self.current_job: Optional[TranscriptionJob] = None
        self.current_job_lock = Lock()

        # Pause/Resume control
        self.pause_event = Event()
        self.pause_event.set()  # Not paused initially

        # Background worker thread
        self.worker_thread = QThread()
        self.worker = TranscriptionWorker(self)
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(self.worker.process_queue)
        self.worker_thread.start()

    def submit_ptt_job(self, audio_data: np.ndarray, language: str,
                       settings: dict, on_complete: Callable) -> str:
        """
        Submit high-priority push-to-talk transcription.
        Pauses any running file transcription.
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

        # Add to database for tracking
        self.db.add_transcription_job(job)

        # Add to priority queue
        self.job_queue.put((job.priority.value, job))

        # If a LOW priority job is running, pause it
        with self.current_job_lock:
            if (self.current_job and
                self.current_job.priority.value > JobPriority.HIGH.value):
                self._pause_current_job()

        return job.id

    def submit_file_job(self, file_path: str, language: str,
                        settings: dict, priority: JobPriority = JobPriority.NORMAL,
                        on_progress: Callable = None,
                        on_complete: Callable = None) -> str:
        """
        Submit file transcription job (single file or batch).
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

        self.db.add_transcription_job(job)
        self.job_queue.put((job.priority.value, job))

        return job.id

    def submit_batch_jobs(self, file_paths: list[str], language: str,
                          settings: dict) -> list[str]:
        """Submit multiple files as LOW priority batch."""
        job_ids = []
        for path in file_paths:
            job_id = self.submit_file_job(
                path, language, settings,
                priority=JobPriority.LOW
            )
            job_ids.append(job_id)
        return job_ids

    def cancel_job(self, job_id: str):
        """Cancel a pending or running job."""
        with self.current_job_lock:
            if self.current_job and self.current_job.id == job_id:
                self.current_job.status = JobStatus.CANCELLED
                self.pause_event.clear()  # Stop processing

    def retry_job(self, job_id: str):
        """Retry a failed job."""
        job = self.db.get_transcription_job(job_id)
        if job and job.status == JobStatus.FAILED:
            job.status = JobStatus.PENDING
            job.current_chunk_index = 0
            job.error_message = ""
            self.db.update_transcription_job(job)
            self.job_queue.put((job.priority.value, job))

    def _pause_current_job(self):
        """Pause the currently running job."""
        if self.current_job:
            self.current_job.status = JobStatus.PAUSED
            self.db.update_transcription_job(self.current_job)
            self.pause_event.clear()
            self.job_paused.emit(self.current_job.id)

    def _resume_job(self, job: TranscriptionJob):
        """Resume a paused job from checkpoint."""
        job.status = JobStatus.RUNNING
        self.db.update_transcription_job(job)
        self.pause_event.set()
        self.job_resumed.emit(job.id)
```

**Worker Thread**:

```python
class TranscriptionWorker(QObject):
    """Background worker that processes the job queue."""

    def __init__(self, manager: TranscriptionQueueManager):
        super().__init__()
        self.manager = manager

    @Slot()
    def process_queue(self):
        """Main loop: continuously process jobs from queue."""
        while True:
            # Block until a job is available
            priority, job = self.manager.job_queue.get()

            with self.manager.current_job_lock:
                self.manager.current_job = job

            try:
                if job.status == JobStatus.CANCELLED:
                    continue

                # Acquire exclusive model access
                with self.manager.model_lock:
                    self._process_job(job)

            except Exception as e:
                job.status = JobStatus.FAILED
                job.error_message = str(e)
                self.manager.db.update_transcription_job(job)
                self.manager.job_failed.emit(job.id, str(e))

            finally:
                with self.manager.current_job_lock:
                    self.manager.current_job = None

    def _process_job(self, job: TranscriptionJob):
        """Process a single transcription job."""
        job.status = JobStatus.RUNNING
        self.manager.db.update_transcription_job(job)
        self.manager.job_started.emit(job.id)

        if job.audio_data is not None:
            # PTT job (in-memory audio)
            result = self._transcribe_audio(job.audio_data, job)
            job.result_text = result['text']

        elif job.file_path is not None:
            # File job (chunked processing with pause support)
            result = self._transcribe_file_chunked(job)
            job.result_text = result

        if job.status != JobStatus.CANCELLED:
            job.status = JobStatus.COMPLETED
            self.manager.db.update_transcription_job(job)
            self.manager.job_completed.emit(job.id, job.result_text)

            if job.on_complete:
                job.on_complete(job.result_text)

    def _transcribe_audio(self, audio: np.ndarray, job: TranscriptionJob) -> dict:
        """Transcribe in-memory audio (PTT)."""
        return self.manager.whisper.transcribe(
            audio,
            language=job.language,
            **job.settings
        )

    def _transcribe_file_chunked(self, job: TranscriptionJob) -> str:
        """
        Transcribe file with chunked processing and pause support.

        Allows:
        - Pausing when high-priority job arrives
        - Resuming from checkpoint
        - Progress reporting
        """
        from app.core.audio_file_loader import load_audio_file

        # Load audio
        audio, sr = load_audio_file(job.file_path)

        # Split into 30-second chunks for checkpointing
        CHUNK_SIZE = 30 * 16000  # 30 seconds at 16kHz
        chunks = [audio[i:i+CHUNK_SIZE] for i in range(0, len(audio), CHUNK_SIZE)]

        job.total_chunks = len(chunks)
        job.completed_chunks = job.current_chunk_index  # Resume from checkpoint

        results = []

        for i in range(job.current_chunk_index, len(chunks)):
            # Check if pause requested
            if not self.manager.pause_event.wait(timeout=0.1):
                # Paused! Save checkpoint
                job.current_chunk_index = i
                self.manager.db.update_transcription_job(job)

                # Wait until resumed or cancelled
                self.manager.pause_event.wait()

                if job.status == JobStatus.CANCELLED:
                    raise RuntimeError("Job cancelled")

            # Transcribe chunk
            chunk_result = self.manager.whisper.transcribe(
                chunks[i],
                language=job.language,
                **job.settings
            )

            results.append(chunk_result['text'])

            # Update progress
            job.completed_chunks = i + 1
            job.current_chunk_index = i + 1
            progress = int((i + 1) / len(chunks) * 100)

            self.manager.db.update_transcription_job(job)
            self.manager.job_progress.emit(job.id, progress)

            if job.on_progress:
                job.on_progress(progress)

        return " ".join(results)
```

**Key Features**:

1. **Priority Queue**: Jobs ordered by priority (HIGH > NORMAL > LOW)
2. **Model Lock**: Only one thread can use WhisperEngine at a time
3. **Pause/Resume**: File jobs checkpoint progress, can be paused by PTT
4. **Batch Support**: Multiple LOW priority jobs queued
5. **Error Recovery**: Failed jobs can be retried
6. **Database Persistence**: Job state survives app restart

---

### Component 2: Enhanced Database Schema

**Location**: `app/data/database.py` (UPDATED)

**New Tables**:

```sql
-- Track transcription jobs (pending, running, completed, failed)
CREATE TABLE transcription_jobs (
    id TEXT PRIMARY KEY,                    -- UUID
    priority INTEGER NOT NULL,              -- 0=HIGH, 1=NORMAL, 2=LOW
    status INTEGER NOT NULL,                -- 0=PENDING, 1=RUNNING, etc.

    -- Job parameters
    file_path TEXT,                         -- NULL for PTT jobs
    language TEXT NOT NULL,
    settings_json TEXT NOT NULL,            -- JSON of whisper settings

    -- Progress tracking
    total_chunks INTEGER DEFAULT 1,
    completed_chunks INTEGER DEFAULT 0,
    current_chunk_index INTEGER DEFAULT 0,

    -- Results
    result_text TEXT,
    error_message TEXT,

    -- Timestamps
    created_at DATETIME DEFAULT (strftime('%Y-%m-%d %H:%M:%f', 'now')),
    started_at DATETIME,
    completed_at DATETIME,

    -- Foreign key to final transcription
    transcription_id INTEGER,
    FOREIGN KEY (transcription_id) REFERENCES transcriptions(id)
);

CREATE INDEX idx_job_status ON transcription_jobs(status, priority);
CREATE INDEX idx_job_created ON transcription_jobs(created_at DESC);

-- Store individual chunks for resumable transcription
CREATE TABLE transcription_chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    text TEXT NOT NULL,
    start_time REAL,                        -- Start time in audio (seconds)
    end_time REAL,                          -- End time in audio (seconds)
    created_at DATETIME DEFAULT (strftime('%Y-%m-%d %H:%M:%f', 'now')),

    FOREIGN KEY (job_id) REFERENCES transcription_jobs(id),
    UNIQUE(job_id, chunk_index)
);

CREATE INDEX idx_chunk_job ON transcription_chunks(job_id, chunk_index);
```

**New DatabaseManager Methods**:

```python
class DatabaseManager:
    # ... existing methods ...

    def add_transcription_job(self, job: TranscriptionJob) -> str:
        """Add a new transcription job."""
        query = """
            INSERT INTO transcription_jobs
            (id, priority, status, file_path, language, settings_json,
             total_chunks, completed_chunks, current_chunk_index)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        self.conn.execute(query, (
            job.id,
            job.priority.value,
            job.status.value,
            job.file_path,
            job.language,
            json.dumps(job.settings),
            job.total_chunks,
            job.completed_chunks,
            job.current_chunk_index
        ))
        self.conn.commit()
        return job.id

    def update_transcription_job(self, job: TranscriptionJob):
        """Update job status and progress."""
        query = """
            UPDATE transcription_jobs
            SET status = ?,
                completed_chunks = ?,
                current_chunk_index = ?,
                result_text = ?,
                error_message = ?,
                started_at = CASE WHEN status = 1 AND started_at IS NULL
                                  THEN strftime('%Y-%m-%d %H:%M:%f', 'now')
                                  ELSE started_at END,
                completed_at = CASE WHEN status IN (3, 4)
                                    THEN strftime('%Y-%m-%d %H:%M:%f', 'now')
                                    ELSE completed_at END
            WHERE id = ?
        """
        self.conn.execute(query, (
            job.status.value,
            job.completed_chunks,
            job.current_chunk_index,
            job.result_text,
            job.error_message,
            job.id
        ))
        self.conn.commit()

    def get_transcription_job(self, job_id: str) -> Optional[TranscriptionJob]:
        """Retrieve a job by ID."""
        query = "SELECT * FROM transcription_jobs WHERE id = ?"
        cursor = self.conn.execute(query, (job_id,))
        row = cursor.fetchone()
        if not row:
            return None

        return TranscriptionJob(
            id=row['id'],
            priority=JobPriority(row['priority']),
            status=JobStatus(row['status']),
            audio_data=None,
            file_path=row['file_path'],
            language=row['language'],
            settings=json.loads(row['settings_json']),
            total_chunks=row['total_chunks'],
            completed_chunks=row['completed_chunks'],
            current_chunk_index=row['current_chunk_index'],
            result_text=row['result_text'] or "",
            error_message=row['error_message'] or ""
        )

    def get_pending_jobs(self) -> list[TranscriptionJob]:
        """Get all pending/paused jobs (for app restart recovery)."""
        query = """
            SELECT * FROM transcription_jobs
            WHERE status IN (0, 2)  -- PENDING or PAUSED
            ORDER BY priority ASC, created_at ASC
        """
        cursor = self.conn.execute(query)
        return [self._row_to_job(row) for row in cursor.fetchall()]

    def add_transcription_chunk(self, job_id: str, chunk_index: int,
                                text: str, start_time: float, end_time: float):
        """Save a completed chunk."""
        query = """
            INSERT OR REPLACE INTO transcription_chunks
            (job_id, chunk_index, text, start_time, end_time)
            VALUES (?, ?, ?, ?, ?)
        """
        self.conn.execute(query, (job_id, chunk_index, text, start_time, end_time))
        self.conn.commit()

    def get_job_chunks(self, job_id: str) -> list[tuple]:
        """Get all chunks for a job (for resuming)."""
        query = """
            SELECT chunk_index, text, start_time, end_time
            FROM transcription_chunks
            WHERE job_id = ?
            ORDER BY chunk_index ASC
        """
        cursor = self.conn.execute(query, (job_id,))
        return cursor.fetchall()
```

**Migration Script**:

```python
# app/data/migrations/002_add_job_tables.py

def upgrade(conn):
    """Add transcription_jobs and transcription_chunks tables."""
    conn.execute("""
        CREATE TABLE transcription_jobs (
            id TEXT PRIMARY KEY,
            priority INTEGER NOT NULL,
            status INTEGER NOT NULL,
            file_path TEXT,
            language TEXT NOT NULL,
            settings_json TEXT NOT NULL,
            total_chunks INTEGER DEFAULT 1,
            completed_chunks INTEGER DEFAULT 0,
            current_chunk_index INTEGER DEFAULT 0,
            result_text TEXT,
            error_message TEXT,
            created_at DATETIME DEFAULT (strftime('%Y-%m-%d %H:%M:%f', 'now')),
            started_at DATETIME,
            completed_at DATETIME,
            transcription_id INTEGER,
            FOREIGN KEY (transcription_id) REFERENCES transcriptions(id)
        )
    """)

    conn.execute("""
        CREATE INDEX idx_job_status ON transcription_jobs(status, priority)
    """)

    conn.execute("""
        CREATE TABLE transcription_chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL,
            chunk_index INTEGER NOT NULL,
            text TEXT NOT NULL,
            start_time REAL,
            end_time REAL,
            created_at DATETIME DEFAULT (strftime('%Y-%m-%d %H:%M:%f', 'now')),
            FOREIGN KEY (job_id) REFERENCES transcription_jobs(id),
            UNIQUE(job_id, chunk_index)
        )
    """)

    conn.execute("""
        CREATE INDEX idx_chunk_job ON transcription_chunks(job_id, chunk_index)
    """)

def downgrade(conn):
    """Remove job tables."""
    conn.execute("DROP TABLE IF EXISTS transcription_chunks")
    conn.execute("DROP TABLE IF EXISTS transcription_jobs")
```

---

### Component 3: Batch Transcription UI

**Location**: `app/ui/batch_transcribe_panel.py` (NEW)

**Design**:

```python
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget,
    QTableWidgetItem, QPushButton, QProgressBar, QLabel,
    QFileDialog, QHeaderView, QAbstractItemView
)
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QColor, QIcon

class FileStatus(Enum):
    PENDING = "⏸️ Pending"
    RUNNING = "▶️ Processing"
    PAUSED = "⏸️ Paused"
    COMPLETED = "✅ Completed"
    FAILED = "❌ Failed"

class BatchTranscribePanel(QWidget):
    """
    Enhanced file transcription panel with batch support.

    Features:
    - Multiple file selection
    - Per-file status tracking
    - Pause/resume batch
    - Retry failed files
    - Real-time progress updates
    """

    # Signals
    batch_started = Signal(list)  # file_paths
    batch_paused = Signal()
    batch_resumed = Signal()
    batch_cancelled = Signal()

    def __init__(self, queue_manager: TranscriptionQueueManager,
                 config: ConfigManager):
        super().__init__()
        self.queue = queue_manager
        self.config = config
        self.job_ids = {}  # file_path -> job_id mapping

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Header
        header = QLabel("Batch File Transcription")
        header.setStyleSheet("font-size: 18px; font-weight: bold;")
        layout.addWidget(header)

        # File list table
        self.file_table = QTableWidget()
        self.file_table.setColumnCount(5)
        self.file_table.setHorizontalHeaderLabels([
            "File Name", "Status", "Progress", "Actions", "Duration"
        ])
        self.file_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Stretch
        )
        self.file_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.file_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        layout.addWidget(self.file_table)

        # Buttons
        button_layout = QHBoxLayout()

        self.add_files_btn = QPushButton("➕ Add Files")
        self.add_files_btn.clicked.connect(self._on_add_files)
        button_layout.addWidget(self.add_files_btn)

        self.remove_files_btn = QPushButton("➖ Remove Selected")
        self.remove_files_btn.clicked.connect(self._on_remove_files)
        button_layout.addWidget(self.remove_files_btn)

        self.start_batch_btn = QPushButton("▶️ Start Batch")
        self.start_batch_btn.clicked.connect(self._on_start_batch)
        button_layout.addWidget(self.start_batch_btn)

        self.pause_batch_btn = QPushButton("⏸️ Pause Batch")
        self.pause_batch_btn.clicked.connect(self._on_pause_batch)
        self.pause_batch_btn.setEnabled(False)
        button_layout.addWidget(self.pause_batch_btn)

        self.cancel_batch_btn = QPushButton("⏹️ Cancel Batch")
        self.cancel_batch_btn.clicked.connect(self._on_cancel_batch)
        self.cancel_batch_btn.setEnabled(False)
        button_layout.addWidget(self.cancel_batch_btn)

        button_layout.addStretch()
        layout.addLayout(button_layout)

        # Overall progress
        progress_layout = QHBoxLayout()
        progress_layout.addWidget(QLabel("Overall Progress:"))

        self.overall_progress = QProgressBar()
        self.overall_progress.setRange(0, 100)
        self.overall_progress.setValue(0)
        progress_layout.addWidget(self.overall_progress)

        self.progress_label = QLabel("0 / 0 files")
        progress_layout.addWidget(self.progress_label)

        layout.addLayout(progress_layout)

    def _connect_signals(self):
        """Connect to queue manager signals."""
        self.queue.job_started.connect(self._on_job_started)
        self.queue.job_progress.connect(self._on_job_progress)
        self.queue.job_paused.connect(self._on_job_paused)
        self.queue.job_resumed.connect(self._on_job_resumed)
        self.queue.job_completed.connect(self._on_job_completed)
        self.queue.job_failed.connect(self._on_job_failed)

    @Slot()
    def _on_add_files(self):
        """Open file dialog to add multiple files."""
        file_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Audio Files",
            self.config.get('file_transcribe.last_directory', ''),
            "Audio Files (*.mp3 *.wav *.m4a *.flac *.ogg *.opus *.webm *.mp4)"
        )

        if not file_paths:
            return

        # Update last directory
        self.config.set('file_transcribe.last_directory',
                        os.path.dirname(file_paths[0]))

        # Add files to table
        for path in file_paths:
            self._add_file_to_table(path)

    def _add_file_to_table(self, file_path: str):
        """Add a file row to the table."""
        row = self.file_table.rowCount()
        self.file_table.insertRow(row)

        # File name
        name_item = QTableWidgetItem(os.path.basename(file_path))
        name_item.setData(Qt.UserRole, file_path)  # Store full path
        self.file_table.setItem(row, 0, name_item)

        # Status
        status_item = QTableWidgetItem(FileStatus.PENDING.value)
        status_item.setForeground(QColor("#888888"))
        self.file_table.setItem(row, 1, status_item)

        # Progress bar
        progress_bar = QProgressBar()
        progress_bar.setRange(0, 100)
        progress_bar.setValue(0)
        self.file_table.setCellWidget(row, 2, progress_bar)

        # Action buttons
        action_widget = QWidget()
        action_layout = QHBoxLayout(action_widget)
        action_layout.setContentsMargins(4, 4, 4, 4)

        retry_btn = QPushButton("🔄 Retry")
        retry_btn.setEnabled(False)
        retry_btn.clicked.connect(lambda: self._retry_file(file_path))
        action_layout.addWidget(retry_btn)

        cancel_btn = QPushButton("✖️ Cancel")
        cancel_btn.setEnabled(False)
        cancel_btn.clicked.connect(lambda: self._cancel_file(file_path))
        action_layout.addWidget(cancel_btn)

        self.file_table.setCellWidget(row, 3, action_widget)

        # Duration (initially unknown)
        duration_item = QTableWidgetItem("--:--")
        self.file_table.setItem(row, 4, duration_item)

    @Slot()
    def _on_start_batch(self):
        """Submit all pending files as batch jobs."""
        file_paths = []

        for row in range(self.file_table.rowCount()):
            status_item = self.file_table.item(row, 1)
            if status_item.text() == FileStatus.PENDING.value:
                name_item = self.file_table.item(row, 0)
                file_paths.append(name_item.data(Qt.UserRole))

        if not file_paths:
            return

        # Get transcription settings
        language = self.config.get('whisper.language')
        settings = {
            'fp16': self.config.get('whisper.fp16'),
            'beam_size': self.config.get('whisper.beam_size'),
            'temperature': self.config.get('whisper.temperature')
        }

        # Submit batch to queue manager
        job_ids = self.queue.submit_batch_jobs(file_paths, language, settings)

        # Store job IDs
        for path, job_id in zip(file_paths, job_ids):
            self.job_ids[path] = job_id

        # Update UI
        self.start_batch_btn.setEnabled(False)
        self.pause_batch_btn.setEnabled(True)
        self.cancel_batch_btn.setEnabled(True)

        self.batch_started.emit(file_paths)

    @Slot(str)
    def _on_job_started(self, job_id: str):
        """Update UI when a job starts."""
        file_path = self._get_file_path_by_job_id(job_id)
        if not file_path:
            return

        row = self._get_row_by_file_path(file_path)
        if row is None:
            return

        # Update status
        status_item = self.file_table.item(row, 1)
        status_item.setText(FileStatus.RUNNING.value)
        status_item.setForeground(QColor("#2196F3"))  # Blue

        # Enable cancel button
        action_widget = self.file_table.cellWidget(row, 3)
        cancel_btn = action_widget.findChild(QPushButton, "",
                                             Qt.FindChildrenRecursively)
        if cancel_btn:
            cancel_btn.setEnabled(True)

    @Slot(str, int)
    def _on_job_progress(self, job_id: str, percentage: int):
        """Update progress bar when job progresses."""
        file_path = self._get_file_path_by_job_id(job_id)
        if not file_path:
            return

        row = self._get_row_by_file_path(file_path)
        if row is None:
            return

        # Update progress bar
        progress_bar = self.file_table.cellWidget(row, 2)
        if isinstance(progress_bar, QProgressBar):
            progress_bar.setValue(percentage)

        # Update overall progress
        self._update_overall_progress()

    @Slot(str, str)
    def _on_job_completed(self, job_id: str, result_text: str):
        """Update UI when job completes successfully."""
        file_path = self._get_file_path_by_job_id(job_id)
        if not file_path:
            return

        row = self._get_row_by_file_path(file_path)
        if row is None:
            return

        # Update status
        status_item = self.file_table.item(row, 1)
        status_item.setText(FileStatus.COMPLETED.value)
        status_item.setForeground(QColor("#4CAF50"))  # Green

        # Set progress to 100%
        progress_bar = self.file_table.cellWidget(row, 2)
        if isinstance(progress_bar, QProgressBar):
            progress_bar.setValue(100)

        # Disable action buttons
        action_widget = self.file_table.cellWidget(row, 3)
        for btn in action_widget.findChildren(QPushButton):
            btn.setEnabled(False)

        # Update overall progress
        self._update_overall_progress()
        self._check_batch_completion()

    @Slot(str, str)
    def _on_job_failed(self, job_id: str, error_message: str):
        """Update UI when job fails."""
        file_path = self._get_file_path_by_job_id(job_id)
        if not file_path:
            return

        row = self._get_row_by_file_path(file_path)
        if row is None:
            return

        # Update status
        status_item = self.file_table.item(row, 1)
        status_item.setText(FileStatus.FAILED.value)
        status_item.setForeground(QColor("#F44336"))  # Red
        status_item.setToolTip(f"Error: {error_message}")

        # Enable retry button, disable cancel
        action_widget = self.file_table.cellWidget(row, 3)
        buttons = action_widget.findChildren(QPushButton)
        if len(buttons) >= 2:
            buttons[0].setEnabled(True)   # Retry
            buttons[1].setEnabled(False)  # Cancel

        # Update overall progress
        self._update_overall_progress()

    def _update_overall_progress(self):
        """Recalculate overall batch progress."""
        total_files = self.file_table.rowCount()
        if total_files == 0:
            return

        completed = 0
        total_progress = 0

        for row in range(total_files):
            status_item = self.file_table.item(row, 1)
            status = status_item.text()

            if status == FileStatus.COMPLETED.value:
                completed += 1
                total_progress += 100
            elif status == FileStatus.RUNNING.value:
                progress_bar = self.file_table.cellWidget(row, 2)
                if isinstance(progress_bar, QProgressBar):
                    total_progress += progress_bar.value()

        overall_percentage = int(total_progress / total_files)
        self.overall_progress.setValue(overall_percentage)
        self.progress_label.setText(f"{completed} / {total_files} files")

    def _check_batch_completion(self):
        """Check if all jobs are done, reset UI if so."""
        all_done = True

        for row in range(self.file_table.rowCount()):
            status_item = self.file_table.item(row, 1)
            status = status_item.text()

            if status in [FileStatus.PENDING.value, FileStatus.RUNNING.value,
                          FileStatus.PAUSED.value]:
                all_done = False
                break

        if all_done:
            self.start_batch_btn.setEnabled(True)
            self.pause_batch_btn.setEnabled(False)
            self.cancel_batch_btn.setEnabled(False)

    def _get_file_path_by_job_id(self, job_id: str) -> Optional[str]:
        """Reverse lookup: job_id -> file_path."""
        for path, jid in self.job_ids.items():
            if jid == job_id:
                return path
        return None

    def _get_row_by_file_path(self, file_path: str) -> Optional[int]:
        """Find table row by file path."""
        for row in range(self.file_table.rowCount()):
            name_item = self.file_table.item(row, 0)
            if name_item.data(Qt.UserRole) == file_path:
                return row
        return None

    def _retry_file(self, file_path: str):
        """Retry a failed file."""
        job_id = self.job_ids.get(file_path)
        if job_id:
            self.queue.retry_job(job_id)

            # Reset UI
            row = self._get_row_by_file_path(file_path)
            if row is not None:
                status_item = self.file_table.item(row, 1)
                status_item.setText(FileStatus.PENDING.value)
                status_item.setForeground(QColor("#888888"))

                progress_bar = self.file_table.cellWidget(row, 2)
                if isinstance(progress_bar, QProgressBar):
                    progress_bar.setValue(0)

    def _cancel_file(self, file_path: str):
        """Cancel a running file."""
        job_id = self.job_ids.get(file_path)
        if job_id:
            self.queue.cancel_job(job_id)
```

**Integration into MainWindow**:

```python
# app/ui/main_window.py

def _setup_ui(self):
    # ... existing code ...

    # Add new "Batch Transcribe" sidebar button
    self.batch_transcribe_btn = self._create_sidebar_button(
        "📂 Batch Files", "batch_transcribe"
    )
    sidebar_layout.addWidget(self.batch_transcribe_btn)

    # Add BatchTranscribePanel to stacked widget
    self.batch_panel = BatchTranscribePanel(
        self.queue_manager,  # Pass queue manager
        self.config_manager
    )
    self.content_stack.addWidget(self.batch_panel)
```

---

### Component 4: Fix History Panel Issues

**Location**: `app/ui/history_panel.py` (UPDATED)

**Issues to Fix**:

1. **Debounce Rapid Reloads**:
```python
from PySide6.QtCore import QTimer

class HistoryPanel(QWidget):
    def __init__(self, db: DatabaseManager):
        super().__init__()
        self.db = db

        # Debounce timer to prevent rapid reloads
        self.reload_timer = QTimer()
        self.reload_timer.setSingleShot(True)
        self.reload_timer.setInterval(300)  # 300ms debounce
        self.reload_timer.timeout.connect(self._perform_reload)

        self._pending_reload = False

    def load_history(self, limit: int = 50):
        """Request a history reload (debounced)."""
        self._pending_reload = True
        self.reload_timer.start()  # Restart timer

    def _perform_reload(self):
        """Actually reload history after debounce period."""
        if not self._pending_reload:
            return

        self._pending_reload = False

        # Fetch transcriptions
        transcriptions = self.db.get_recent_transcriptions(limit=50)

        # Update UI (only if content changed)
        if self._has_content_changed(transcriptions):
            self._update_list_widget(transcriptions)
```

2. **Filter by Source Type**:
```python
# Add filter buttons to UI
def _setup_ui(self):
    # ... existing code ...

    filter_layout = QHBoxLayout()

    self.filter_all_btn = QPushButton("All")
    self.filter_all_btn.setCheckable(True)
    self.filter_all_btn.setChecked(True)
    self.filter_all_btn.clicked.connect(lambda: self._set_filter(None))
    filter_layout.addWidget(self.filter_all_btn)

    self.filter_ptt_btn = QPushButton("🎤 Push-to-Talk")
    self.filter_ptt_btn.setCheckable(True)
    self.filter_ptt_btn.clicked.connect(lambda: self._set_filter('microphone'))
    filter_layout.addWidget(self.filter_ptt_btn)

    self.filter_file_btn = QPushButton("📁 Files")
    self.filter_file_btn.setCheckable(True)
    self.filter_file_btn.clicked.connect(lambda: self._set_filter('file'))
    filter_layout.addWidget(self.filter_file_btn)

    layout.addLayout(filter_layout)

def _set_filter(self, source_type: Optional[str]):
    """Filter history by source type."""
    self.current_filter = source_type

    # Update button states
    self.filter_all_btn.setChecked(source_type is None)
    self.filter_ptt_btn.setChecked(source_type == 'microphone')
    self.filter_file_btn.setChecked(source_type == 'file')

    # Reload with filter
    self.load_history()

def _perform_reload(self):
    # ... existing code ...

    # Apply filter
    if self.current_filter:
        transcriptions = [
            t for t in transcriptions
            if t.get('source_type') == self.current_filter
        ]

    # ... rest of method ...
```

**Location**: `app/core/file_transcription_worker.py` (FIX)

**Fix Incorrect Source Type**:

```python
# Line 224 - BEFORE:
db.add_transcription(
    text=text,
    language=result.get('language'),
    duration=duration,
    model_used=self.whisper_engine.current_model,
    audio_path=self.file_path,
    source_type='microphone'  # ← BUG!
)

# Line 224 - AFTER:
db.add_transcription(
    text=text,
    language=result.get('language'),
    duration=duration,
    model_used=self.whisper_engine.current_model,
    audio_path=self.file_path,
    source_type='file'  # ← FIXED!
)
```

---

### Component 5: Update Main Application

**Location**: `app/main.py` (UPDATED)

**Changes**:

1. **Initialize TranscriptionQueueManager**:

```python
class WhisperFreeApp:
    def __init__(self):
        # ... existing code ...

        # Initialize queue manager AFTER whisper engine
        self.queue_manager = TranscriptionQueueManager(
            whisper_engine=self.whisper,
            db=self.db
        )

        # Pass queue_manager to UI components
        self.main_window = MainWindow(
            config_manager=self.config,
            db_manager=self.db,
            state_machine=self.state,
            queue_manager=self.queue_manager  # NEW
        )
```

2. **Refactor PTT to Use Queue Manager**:

```python
@Slot(np.ndarray)
def on_recording_stopped(self, audio_data: np.ndarray):
    """Handle recording stopped - submit to queue instead of direct transcription."""
    logger.info(f"Recording stopped, captured {len(audio_data)} samples")

    # Get settings
    language = self.config.get('whisper.language')
    settings = {
        'fp16': self.config.get('whisper.fp16'),
        'beam_size': self.config.get('whisper.beam_size'),
        'temperature': self.config.get('whisper.temperature')
    }

    # Submit high-priority PTT job to queue
    job_id = self.queue_manager.submit_ptt_job(
        audio_data=audio_data,
        language=language,
        settings=settings,
        on_complete=self._on_ptt_complete
    )

    logger.info(f"Submitted PTT job {job_id} to queue")

def _on_ptt_complete(self, result_text: str):
    """Callback when PTT transcription completes."""
    # Existing completion logic
    self.on_transcription_complete(result_text, language='en', duration=0.0)
```

3. **Remove Duplicate Thread Starts**:

```python
# BEFORE (Lines 305-307):
self.transcription_thread.start()

self.transcription_thread.start()  # DUPLICATE!

# AFTER:
self.transcription_thread.start()  # Keep only one
```

4. **Fix Duplicate Error Handler**:

```python
# BEFORE: Two handlers named on_recording_error()
# Lines 415-424 and 479-488

# AFTER: Rename to distinguish them
@Slot(str)
def on_start_recording_error(self, error: str):
    """Handle errors from starting recording."""
    logger.error(f"Start recording error: {error}")
    # ... existing handling ...

@Slot(str)
def on_stop_recording_error(self, error: str):
    """Handle errors from stopping recording."""
    logger.error(f"Stop recording error: {error}")
    # ... existing handling ...

# Update signal connections:
self.start_recording_worker.error.connect(self.on_start_recording_error)
self.stop_recording_worker.error.connect(self.on_stop_recording_error)
```

---

## Implementation Plan

### Phase 1: Critical Fixes (Week 1)

**Priority**: 🔴 Critical

**Tasks**:

1. **Fix KV Cache Corruption** (2 days)
   - [ ] Create `TranscriptionQueueManager` class
   - [ ] Add `threading.Lock()` for model access
   - [ ] Implement priority queue (HIGH for PTT, LOW for files)
   - [ ] Test concurrent PTT + file transcription
   - [ ] Verify no more "Key and Value sequence length" errors

2. **Fix History Panel Issues** (1 day)
   - [ ] Change `source_type` from `'microphone'` to `'file'` in FileTranscriptionWorker line 224
   - [ ] Add reload debouncing (300ms timer)
   - [ ] Add `_has_content_changed()` check before UI update
   - [ ] Test that windows no longer flash after file transcription

3. **Fix Code Quality Issues** (0.5 days)
   - [ ] Remove duplicate `transcription_thread.start()` call
   - [ ] Rename duplicate `on_recording_error()` handlers
   - [ ] Add proper error handling for both start/stop recording

**Success Criteria**:
- ✅ PTT works during file transcription without errors
- ✅ History panel updates smoothly without visual glitches
- ✅ No duplicate error handlers or thread starts

---

### Phase 2: Database Schema & Job Management (Week 2)

**Priority**: 🟡 High

**Tasks**:

1. **Database Schema Update** (1 day)
   - [ ] Create migration script `002_add_job_tables.py`
   - [ ] Add `transcription_jobs` table
   - [ ] Add `transcription_chunks` table
   - [ ] Add indices for performance
   - [ ] Write upgrade/downgrade functions

2. **Implement DatabaseManager Methods** (1 day)
   - [ ] `add_transcription_job()`
   - [ ] `update_transcription_job()`
   - [ ] `get_transcription_job()`
   - [ ] `get_pending_jobs()`
   - [ ] `add_transcription_chunk()`
   - [ ] `get_job_chunks()`
   - [ ] Write unit tests

3. **TranscriptionQueueManager Implementation** (2 days)
   - [ ] Implement `submit_ptt_job()`
   - [ ] Implement `submit_file_job()`
   - [ ] Implement `submit_batch_jobs()`
   - [ ] Implement `cancel_job()`
   - [ ] Implement `retry_job()`
   - [ ] Implement `_pause_current_job()`
   - [ ] Implement `_resume_job()`
   - [ ] Create `TranscriptionWorker` background thread
   - [ ] Add comprehensive logging

**Success Criteria**:
- ✅ Database migrations run successfully
- ✅ Job status persists across app restarts
- ✅ Queue manager handles job lifecycle

---

### Phase 3: Pause/Resume File Transcription (Week 3)

**Priority**: 🟡 High

**Tasks**:

1. **Chunked File Processing** (2 days)
   - [ ] Refactor `FileTranscriptionWorker` to process 30s chunks
   - [ ] Implement checkpoint saving after each chunk
   - [ ] Implement resume from checkpoint
   - [ ] Store chunks in `transcription_chunks` table
   - [ ] Add progress tracking per chunk

2. **Pause/Resume Logic** (2 days)
   - [ ] Add `pause_event` (threading.Event) to queue manager
   - [ ] Detect when HIGH priority job arrives
   - [ ] Pause LOW priority job gracefully
   - [ ] Save checkpoint with current chunk index
   - [ ] Resume job after HIGH priority completes
   - [ ] Test PTT interrupting file transcription

3. **Testing** (1 day)
   - [ ] Test: Long file (40 min) → PTT at 20 min → resume
   - [ ] Test: Multiple PTT interruptions during one file
   - [ ] Test: App restart during paused transcription (recovery)
   - [ ] Test: Chunk boundaries are seamless in final transcript

**Success Criteria**:
- ✅ File transcription pauses when PTT triggered
- ✅ File transcription resumes from exact position after PTT
- ✅ Final transcript is identical to non-interrupted version

---

### Phase 4: Batch Transcription UI (Week 4)

**Priority**: 🟢 Medium

**Tasks**:

1. **Create BatchTranscribePanel** (2 days)
   - [ ] Create `app/ui/batch_transcribe_panel.py`
   - [ ] Design table layout (file, status, progress, actions, duration)
   - [ ] Implement "Add Files" multi-select dialog
   - [ ] Implement "Remove Selected" button
   - [ ] Add status icons (⏸️ Pending, ▶️ Running, ✅ Complete, ❌ Failed)
   - [ ] Add per-file progress bars
   - [ ] Add overall batch progress bar

2. **Integrate with Queue Manager** (1 day)
   - [ ] Connect signals (job_started, job_progress, job_completed, job_failed)
   - [ ] Submit batch jobs via `submit_batch_jobs()`
   - [ ] Update UI based on job status changes
   - [ ] Implement retry button for failed files
   - [ ] Implement cancel button for running files

3. **Add to MainWindow** (1 day)
   - [ ] Add "Batch Files" sidebar button
   - [ ] Add BatchTranscribePanel to stacked widget
   - [ ] Wire up navigation
   - [ ] Test UI responsiveness during batch processing

**Success Criteria**:
- ✅ Users can select and transcribe 10+ files
- ✅ Each file shows individual status and progress
- ✅ Failed files can be retried without re-adding
- ✅ Batch respects PTT interruptions (all files pause)

---

### Phase 5: Polish & Documentation (Week 5)

**Priority**: 🟢 Low

**Tasks**:

1. **Error Messages** (1 day)
   - [ ] User-friendly error dialogs
   - [ ] Detailed error tooltips in batch UI
   - [ ] Log rotation and cleanup
   - [ ] Sentry/crash reporting integration

2. **Performance Optimization** (1 day)
   - [ ] Profile database queries (add indices if needed)
   - [ ] Optimize chunk size (test 15s vs 30s vs 60s)
   - [ ] Lazy-load history panel (pagination)
   - [ ] Reduce UI update frequency during batch

3. **Documentation** (1 day)
   - [ ] Update README with batch transcription guide
   - [ ] Add architecture diagram
   - [ ] Document new database schema
   - [ ] Write migration guide for existing users

4. **Testing** (2 days)
   - [ ] Integration tests for full workflow
   - [ ] Load testing (100 files in batch)
   - [ ] Memory leak testing (long-running transcription)
   - [ ] Edge case testing (corrupted files, disk full, etc.)

**Success Criteria**:
- ✅ All tests pass
- ✅ Documentation is complete
- ✅ Performance is acceptable (no UI lag)

---

## Testing Strategy

### Unit Tests

**Locations**:
- `tests/test_queue_manager.py` (NEW)
- `tests/test_database.py` (UPDATED)
- `tests/test_chunked_processing.py` (NEW)

**Test Cases**:

1. **TranscriptionQueueManager**:
   ```python
   def test_ptt_interrupts_file_transcription():
       """Verify HIGH priority jobs pause LOW priority jobs."""

   def test_job_resume_from_checkpoint():
       """Verify paused jobs resume from correct chunk."""

   def test_concurrent_model_access_blocked():
       """Verify only one job can use model at a time."""

   def test_batch_jobs_process_sequentially():
       """Verify batch files process one-by-one."""
   ```

2. **Database**:
   ```python
   def test_job_persistence():
       """Verify job state survives app restart."""

   def test_chunk_storage():
       """Verify chunks are stored and retrieved correctly."""

   def test_migration_002():
       """Verify schema migration runs successfully."""
   ```

3. **Chunked Processing**:
   ```python
   def test_chunk_boundaries():
       """Verify chunks don't cut off words mid-sentence."""

   def test_pause_resume_accuracy():
       """Verify resumed transcription matches non-interrupted."""
   ```

---

### Integration Tests

**Locations**:
- `tests/integration/test_ptt_file_concurrent.py` (NEW)
- `tests/integration/test_batch_workflow.py` (NEW)

**Test Scenarios**:

1. **Concurrent PTT + File**:
   ```
   1. Start file transcription (40 min audio)
   2. Wait 10 seconds
   3. Trigger PTT recording (5 sec audio)
   4. Verify file pauses
   5. Verify PTT completes successfully
   6. Verify file resumes from correct position
   7. Verify final file transcription is complete
   ```

2. **Batch Workflow**:
   ```
   1. Add 10 audio files to batch
   2. Start batch
   3. Verify files process sequentially
   4. Fail file #5 (simulate error)
   5. Verify batch continues with file #6
   6. Retry file #5
   7. Verify retry succeeds
   8. Verify all 10 files complete
   ```

3. **App Restart Recovery**:
   ```
   1. Start long file transcription
   2. Kill app mid-transcription
   3. Restart app
   4. Verify job is marked as PAUSED in database
   5. Resume job
   6. Verify transcription continues from checkpoint
   ```

---

### Manual Testing Checklist

**UI Testing**:
- [ ] History panel doesn't flash when adding transcriptions
- [ ] Batch table updates smoothly during processing
- [ ] Progress bars animate correctly
- [ ] Status icons display correctly (⏸️ ▶️ ✅ ❌)
- [ ] Retry/Cancel buttons enable/disable appropriately
- [ ] Overlay shows correct status during PTT
- [ ] No visual glitches or freezing

**Workflow Testing**:
- [ ] PTT works during file transcription
- [ ] File transcription pauses/resumes correctly
- [ ] Batch processing handles 20+ files
- [ ] Failed files can be retried individually
- [ ] Cancelled jobs don't resume
- [ ] App restart recovers in-progress jobs

**Error Handling**:
- [ ] Corrupted audio file shows error message
- [ ] Disk full during transcription shows error
- [ ] GPU out of memory shows error
- [ ] Network error (if fetching remote files) shows error
- [ ] Database locked shows error and retries

---

## Migration & Rollback

### Migration Steps

**For Existing Users**:

1. **Backup Database**:
   ```bash
   cp ~/.config/whisper-free/history.db ~/.config/whisper-free/history.db.backup
   ```

2. **Run Migration**:
   ```python
   # Auto-run on app start
   from app.data.database import DatabaseManager

   db = DatabaseManager()
   db.migrate_schema()  # Runs 002_add_job_tables.py
   ```

3. **Verify Migration**:
   ```sql
   -- Check new tables exist
   SELECT name FROM sqlite_master WHERE type='table';

   -- Should include:
   -- transcriptions (existing)
   -- transcription_jobs (new)
   -- transcription_chunks (new)
   ```

4. **Test Functionality**:
   - Start PTT transcription
   - Start file transcription
   - Verify both work without errors

---

### Rollback Procedure

**If Issues Occur**:

1. **Stop Application**:
   ```bash
   pkill -f "python -m app.main"
   ```

2. **Restore Database**:
   ```bash
   cp ~/.config/whisper-free/history.db.backup ~/.config/whisper-free/history.db
   ```

3. **Revert Code**:
   ```bash
   git checkout main  # Or previous stable tag
   ```

4. **Restart Application**:
   ```bash
   python -m app.main
   ```

---

### Compatibility Notes

**Backwards Compatibility**:
- Existing transcriptions in database remain intact
- Old config files are compatible (new settings have defaults)
- Users can continue using single-file transcription as before
- Batch transcription is opt-in (new UI panel)

**Forward Compatibility**:
- New database schema is additive (no columns removed)
- Migration is non-destructive (existing data preserved)
- Downgrade is possible (new tables ignored by old code)

---

## Summary

This comprehensive plan addresses all reported issues and feature requests:

### Critical Fixes ✅
1. **KV Cache Corruption**: Fixed via exclusive model locking in TranscriptionQueueManager
2. **History Panel Glitches**: Fixed via debouncing and correct source_type
3. **Concurrent Transcription**: Enabled via priority queue system

### New Features ✅
1. **Pause/Resume**: File transcription pauses for PTT, resumes after
2. **Batch Transcription**: Multiple file processing with per-file status
3. **Error Recovery**: Individual file retry without re-adding entire batch
4. **Job Persistence**: Transcription state survives app restart

### Implementation Timeline
- **Week 1**: Critical fixes (KV cache, history panel, code quality)
- **Week 2**: Database schema and job management
- **Week 3**: Pause/resume functionality
- **Week 4**: Batch transcription UI
- **Week 5**: Polish, testing, documentation

### Risk Mitigation
- Incremental rollout (phase by phase)
- Comprehensive unit and integration tests
- Database backups before migration
- Rollback procedure documented
- Backwards compatibility maintained

---

## Next Steps

1. **Review This Plan**: Discuss priorities and timeline
2. **Set Up Development Environment**: Create feature branch
3. **Begin Phase 1**: Start with critical KV cache fix
4. **Iterate**: Gather feedback after each phase

**Questions?** Review specific sections or adjust priorities as needed.

---

*Plan created: 2026-01-30*
*Last updated: 2026-01-30*
*Status: Ready for implementation*
