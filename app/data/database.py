"""
DatabaseManager - SQLite database for transcription history

Manages persistent storage of all transcriptions with timestamps,
language info, and metadata. Provides search, export, and cleanup.
"""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Dict, Any
import logging
import json
import threading

logger = logging.getLogger(__name__)


class DatabaseManager:
    """
    Manages SQLite database for transcription history.

    Stores all transcriptions with timestamps, language info, and metadata.
    Provides search, export, and cleanup functionality.
    """

    def __init__(self, db_path: str = "~/.config/whisper-free/history.db"):
        """
        Initialize database manager.

        Args:
            db_path: Path to SQLite database file

        Creates database and tables if they don't exist.
        """
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info(f"Initializing database at {self.db_path}")

        # Connect to database
        self.conn = sqlite3.connect(
            str(self.db_path),
            check_same_thread=False,  # Allow multi-threaded access for Qt
            isolation_level=None  # Autocommit mode for thread safety
        )
        self.conn.row_factory = sqlite3.Row  # Enable column access by name

        # Thread lock for database operations
        self._db_lock = threading.Lock()

        # Enable foreign keys
        self.conn.execute("PRAGMA foreign_keys = ON")

        # Create tables if they don't exist
        self._create_tables()

    def _create_tables(self) -> None:
        """Create database tables and indices if they don't exist."""
        try:
            cursor = self.conn.cursor()

            # Create main transcriptions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS transcriptions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME DEFAULT (strftime('%Y-%m-%d %H:%M:%f', 'now')),
                    text TEXT NOT NULL,
                    language TEXT,
                    duration REAL,
                    model_used TEXT,
                    audio_path TEXT,
                    source_type TEXT DEFAULT 'microphone',
                    output_path TEXT
                )
            """)

            # Migrate existing databases: add new columns if they don't exist
            try:
                cursor.execute("SELECT source_type FROM transcriptions LIMIT 1")
            except sqlite3.OperationalError:
                # Column doesn't exist, add it
                logger.info("Adding source_type column to existing database")
                cursor.execute("ALTER TABLE transcriptions ADD COLUMN source_type TEXT DEFAULT 'microphone'")

            try:
                cursor.execute("SELECT output_path FROM transcriptions LIMIT 1")
            except sqlite3.OperationalError:
                # Column doesn't exist, add it
                logger.info("Adding output_path column to existing database")
                cursor.execute("ALTER TABLE transcriptions ADD COLUMN output_path TEXT")

            # Create indices for performance
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_timestamp
                ON transcriptions(timestamp DESC, id DESC)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_text_search
                ON transcriptions(text)
            """)

            # Create transcription_jobs table (for job management and pause/resume)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS transcription_jobs (
                    id TEXT PRIMARY KEY,
                    priority INTEGER NOT NULL,
                    status INTEGER NOT NULL,
                    file_path TEXT,
                    language TEXT,
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

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_job_status
                ON transcription_jobs(status, priority)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_job_created
                ON transcription_jobs(created_at DESC)
            """)

            # Create transcription_chunks table (for resumable chunked processing)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS transcription_chunks (
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

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_chunk_job
                ON transcription_chunks(job_id, chunk_index)
            """)

            self.conn.commit()
            logger.info("Database tables created successfully")

        except sqlite3.Error as e:
            logger.error(f"Error creating tables: {e}")
            raise RuntimeError(f"Failed to create database tables: {e}")

    def add_transcription(
        self,
        text: str,
        language: Optional[str] = None,
        duration: float = 0.0,
        model_used: str = "",
        audio_path: Optional[str] = None,
        source_type: str = 'microphone',
        output_path: Optional[str] = None
    ) -> int:
        """
        Insert new transcription into database.

        Args:
            text: Transcribed text
            language: Language code (e.g., 'en', 'es')
            duration: Audio duration in seconds
            model_used: Whisper model name used
            audio_path: Optional path to saved audio file
            source_type: 'microphone' or 'file' (default: 'microphone')
            output_path: Optional path to saved .txt output file

        Returns:
            Row ID of inserted transcription
        """
        if not text or not text.strip():
            raise ValueError("Transcription text cannot be empty")

        try:
            with self._db_lock:
                cursor = self.conn.cursor()
                cursor.execute("""
                    INSERT INTO transcriptions
                    (text, language, duration, model_used, audio_path, source_type, output_path)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (text.strip(), language, duration, model_used, audio_path, source_type, output_path))

                row_id = cursor.lastrowid

                logger.info(f"Added transcription ID {row_id} ({len(text)} chars, source={source_type})")
                return row_id

        except sqlite3.Error as e:
            logger.error(f"Error adding transcription: {e}")
            raise RuntimeError(f"Failed to add transcription: {e}")

    def _format_timestamp(self, timestamp_str: str) -> str:
        """
        Format timestamp for display.

        Args:
            timestamp_str: ISO format timestamp string

        Returns:
            Formatted string like "Today at 2:34 PM" or "Jan 18 at 2:34 PM"
        """
        try:
            dt = datetime.fromisoformat(timestamp_str)
            now = datetime.now()

            # Format time part
            time_str = dt.strftime("%-I:%M %p")  # "2:34 PM"

            # Determine date part
            if dt.date() == now.date():
                return f"Today at {time_str}"
            elif dt.date() == (now - timedelta(days=1)).date():
                return f"Yesterday at {time_str}"
            else:
                date_str = dt.strftime("%b %-d")  # "Jan 18"
                return f"{date_str} at {time_str}"

        except Exception as e:
            logger.warning(f"Error formatting timestamp: {e}")
            return timestamp_str

    def get_recent_transcriptions(self, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        """
        Get recent transcriptions ordered by timestamp with pagination support.

        Args:
            limit: Maximum number of results (default: 50)
            offset: Number of results to skip (default: 0)

        Returns:
            List of dicts with keys:
                - id: int
                - timestamp: str (formatted like "Today at 2:34 PM")
                - text: str
                - language: str
                - duration: float
                - model_used: str
                - source_type: str
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT id, timestamp, text, language, duration, model_used, source_type
                FROM transcriptions
                ORDER BY timestamp DESC, id DESC
                LIMIT ? OFFSET ?
            """, (limit, offset))

            results = []
            for row in cursor.fetchall():
                results.append({
                    'id': row['id'],
                    'timestamp': self._format_timestamp(row['timestamp']),
                    'text': row['text'],
                    'language': row['language'] or '',
                    'duration': row['duration'] or 0.0,
                    'model_used': row['model_used'] or '',
                    'source_type': row['source_type'] or 'microphone'
                })

            logger.debug(f"Retrieved {len(results)} transcriptions (offset={offset})")
            return results

        except sqlite3.Error as e:
            logger.error(f"Error getting recent transcriptions: {e}")
            raise RuntimeError(f"Failed to get recent transcriptions: {e}")

    def get_transcription_count(self) -> int:
        """
        Get total count of transcriptions in database.

        Returns:
            Total number of transcriptions
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT COUNT(*) as count FROM transcriptions")
            row = cursor.fetchone()
            count = row['count'] if row else 0
            logger.debug(f"Total transcriptions: {count}")
            return count
        except sqlite3.Error as e:
            logger.error(f"Error getting transcription count: {e}")
            return 0

    def search_transcriptions(self, query: str) -> List[Dict[str, Any]]:
        """
        Search transcriptions by text content (case-insensitive).

        Args:
            query: Search query string

        Returns:
            List of matching transcriptions (same format as get_recent)
        """
        if not query or not query.strip():
            return []

        try:
            cursor = self.conn.cursor()

            # Case-insensitive search using LIKE
            search_pattern = f"%{query.strip()}%"
            cursor.execute("""
                SELECT id, timestamp, text, language, duration, model_used
                FROM transcriptions
                WHERE text LIKE ?
                ORDER BY timestamp DESC, id DESC
            """, (search_pattern,))

            results = []
            for row in cursor.fetchall():
                results.append({
                    'id': row['id'],
                    'timestamp': self._format_timestamp(row['timestamp']),
                    'text': row['text'],
                    'language': row['language'] or '',
                    'duration': row['duration'] or 0.0,
                    'model_used': row['model_used'] or ''
                })

            logger.info(f"Search for '{query}' found {len(results)} results")
            return results

        except sqlite3.Error as e:
            logger.error(f"Error searching transcriptions: {e}")
            raise RuntimeError(f"Failed to search transcriptions: {e}")

    def export_to_txt(self, filepath: str) -> None:
        """
        Export all transcriptions to text file.

        Format:
            [2026-01-18 14:32:15]
            This is the transcribed text...

            [2026-01-18 14:35:20]
            Another transcription...
        """
        filepath = Path(filepath).expanduser()
        filepath.parent.mkdir(parents=True, exist_ok=True)

        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT timestamp, text
                FROM transcriptions
                ORDER BY timestamp ASC
            """)

            with open(filepath, 'w', encoding='utf-8') as f:
                for row in cursor.fetchall():
                    # Parse and format timestamp
                    dt = datetime.fromisoformat(row['timestamp'])
                    timestamp_str = dt.strftime("%Y-%m-%d %H:%M:%S")

                    f.write(f"[{timestamp_str}]\n")
                    f.write(f"{row['text']}\n\n")

            logger.info(f"Exported transcriptions to TXT: {filepath}")

        except (sqlite3.Error, IOError) as e:
            logger.error(f"Error exporting to TXT: {e}")
            raise RuntimeError(f"Failed to export to TXT: {e}")

    def export_to_json(self, filepath: str) -> None:
        """
        Export all transcriptions to JSON file.

        Format:
            [
                {
                    "id": 1,
                    "timestamp": "2026-01-18T14:32:15",
                    "text": "...",
                    "language": "en",
                    "duration": 5.2,
                    "model_used": "small"
                },
                ...
            ]
        """
        filepath = Path(filepath).expanduser()
        filepath.parent.mkdir(parents=True, exist_ok=True)

        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT id, timestamp, text, language, duration, model_used, audio_path
                FROM transcriptions
                ORDER BY timestamp ASC
            """)

            results = []
            for row in cursor.fetchall():
                results.append({
                    'id': row['id'],
                    'timestamp': row['timestamp'],
                    'text': row['text'],
                    'language': row['language'],
                    'duration': row['duration'],
                    'model_used': row['model_used'],
                    'audio_path': row['audio_path']
                })

            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2, ensure_ascii=False)

            logger.info(f"Exported {len(results)} transcriptions to JSON: {filepath}")

        except (sqlite3.Error, IOError) as e:
            logger.error(f"Error exporting to JSON: {e}")
            raise RuntimeError(f"Failed to export to JSON: {e}")

    def cleanup_old(self, days: int) -> int:
        """
        Delete transcriptions older than specified days.

        Args:
            days: Delete entries older than this many days

        Returns:
            Number of rows deleted
        """
        if days < 0:
            raise ValueError("Days must be non-negative")

        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                DELETE FROM transcriptions
                WHERE timestamp < datetime('now', ?)
            """, (f'-{days} days',))

            self.conn.commit()
            deleted_count = cursor.rowcount

            logger.info(f"Cleaned up {deleted_count} transcriptions older than {days} days")
            return deleted_count

        except sqlite3.Error as e:
            logger.error(f"Error cleaning up old transcriptions: {e}")
            raise RuntimeError(f"Failed to cleanup old transcriptions: {e}")

    def clear_history(self) -> int:
        """
        Delete ALL transcriptions from the database.

        Returns:
            Number of rows deleted
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("DELETE FROM transcriptions")
            
            self.conn.commit()
            deleted_count = cursor.rowcount
            
            logger.info(f"Cleared all history: {deleted_count} transcriptions deleted")
            return deleted_count

        except sqlite3.Error as e:
            logger.error(f"Error clearing history: {e}")
            raise RuntimeError(f"Failed to clear history: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """
        Get database statistics.

        Returns:
            {
                'total_count': int,
                'total_duration': float (in seconds),
                'languages': dict (language -> count),
                'oldest_date': str,
                'newest_date': str
            }
        """
        try:
            cursor = self.conn.cursor()

            # Get total count
            cursor.execute("SELECT COUNT(*) as count FROM transcriptions")
            total_count = cursor.fetchone()['count']

            # Get total duration
            cursor.execute("SELECT SUM(duration) as total FROM transcriptions")
            total_duration = cursor.fetchone()['total'] or 0.0

            # Get language distribution
            cursor.execute("""
                SELECT language, COUNT(*) as count
                FROM transcriptions
                WHERE language IS NOT NULL
                GROUP BY language
            """)
            languages = {row['language']: row['count'] for row in cursor.fetchall()}

            # Get date range
            cursor.execute("""
                SELECT MIN(timestamp) as oldest, MAX(timestamp) as newest
                FROM transcriptions
            """)
            row = cursor.fetchone()
            oldest_date = row['oldest'] or ''
            newest_date = row['newest'] or ''

            stats = {
                'total_count': total_count,
                'total_duration': total_duration,
                'languages': languages,
                'oldest_date': oldest_date,
                'newest_date': newest_date
            }

            logger.debug(f"Database stats: {stats}")
            return stats

        except sqlite3.Error as e:
            logger.error(f"Error getting stats: {e}")
            raise RuntimeError(f"Failed to get database stats: {e}")

    # ==================== Job Management Methods ====================

    def add_transcription_job(
        self,
        job_id: str,
        priority: int,
        status: int,
        file_path: Optional[str] = None,
        language: Optional[str] = None,
        settings: Optional[Dict[str, Any]] = None,
        total_chunks: int = 1,
        completed_chunks: int = 0,
        current_chunk_index: int = 0
    ) -> str:
        """
        Add a new transcription job to the database.

        Args:
            job_id: Unique job identifier
            priority: Job priority (0=HIGH, 1=NORMAL, 2=LOW)
            status: Job status (0=PENDING, 1=RUNNING, 2=PAUSED, 3=COMPLETED, 4=FAILED, 5=CANCELLED)
            file_path: Path to audio file (None for PTT jobs)
            language: Language code or None for auto-detect
            settings: Whisper transcription settings dictionary
            total_chunks: Total number of chunks for chunked processing
            completed_chunks: Number of completed chunks
            current_chunk_index: Current chunk being processed

        Returns:
            Job ID
        """
        try:
            settings_json = json.dumps(settings or {})

            query = """
                INSERT INTO transcription_jobs
                (id, priority, status, file_path, language, settings_json,
                 total_chunks, completed_chunks, current_chunk_index)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """

            with self._db_lock:
                self.conn.execute(query, (
                    job_id,
                    priority,
                    status,
                    file_path,
                    language,
                    settings_json,
                    total_chunks,
                    completed_chunks,
                    current_chunk_index
                ))

            logger.info(f"Added job {job_id} to database")
            return job_id

        except sqlite3.Error as e:
            logger.error(f"Error adding job: {e}")
            raise RuntimeError(f"Failed to add job to database: {e}")

    def update_transcription_job(
        self,
        job_id: str,
        status: Optional[int] = None,
        completed_chunks: Optional[int] = None,
        current_chunk_index: Optional[int] = None,
        result_text: Optional[str] = None,
        error_message: Optional[str] = None,
        transcription_id: Optional[int] = None
    ) -> None:
        """
        Update an existing transcription job.

        Args:
            job_id: Job ID to update
            status: New status value
            completed_chunks: Updated completed chunks count
            current_chunk_index: Updated current chunk index
            result_text: Final transcription result
            error_message: Error message if failed
            transcription_id: Foreign key to transcriptions table
        """
        try:
            # Build dynamic UPDATE query based on provided parameters
            updates = []
            params = []

            if status is not None:
                updates.append("status = ?")
                params.append(status)

            if completed_chunks is not None:
                updates.append("completed_chunks = ?")
                params.append(completed_chunks)

            if current_chunk_index is not None:
                updates.append("current_chunk_index = ?")
                params.append(current_chunk_index)

            if result_text is not None:
                updates.append("result_text = ?")
                params.append(result_text)

            if error_message is not None:
                updates.append("error_message = ?")
                params.append(error_message)

            if transcription_id is not None:
                updates.append("transcription_id = ?")
                params.append(transcription_id)

            # Update timestamps based on status
            if status == 1:  # RUNNING
                updates.append("""started_at = CASE WHEN started_at IS NULL
                                  THEN strftime('%Y-%m-%d %H:%M:%f', 'now')
                                  ELSE started_at END""")
            elif status in [3, 4, 5]:  # COMPLETED, FAILED, CANCELLED
                updates.append("completed_at = strftime('%Y-%m-%d %H:%M:%f', 'now')")

            if not updates:
                logger.warning(f"No updates provided for job {job_id}")
                return

            params.append(job_id)
            query = f"UPDATE transcription_jobs SET {', '.join(updates)} WHERE id = ?"

            with self._db_lock:
                self.conn.execute(query, params)

            logger.debug(f"Updated job {job_id}")

        except sqlite3.Error as e:
            logger.error(f"Error updating job: {e}")
            raise RuntimeError(f"Failed to update job: {e}")

    def get_transcription_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a transcription job by ID.

        Args:
            job_id: Job ID to retrieve

        Returns:
            Dictionary with job data, or None if not found
        """
        try:
            query = "SELECT * FROM transcription_jobs WHERE id = ?"
            cursor = self.conn.execute(query, (job_id,))
            row = cursor.fetchone()

            if not row:
                return None

            # Convert row to dictionary
            job = dict(row)

            # Parse JSON settings
            if job.get('settings_json'):
                job['settings'] = json.loads(job['settings_json'])
            else:
                job['settings'] = {}

            return job

        except sqlite3.Error as e:
            logger.error(f"Error getting job: {e}")
            raise RuntimeError(f"Failed to get job: {e}")

    def get_pending_jobs(self) -> List[Dict[str, Any]]:
        """
        Get all pending or paused jobs (for recovery on app restart).

        Returns:
            List of job dictionaries, ordered by priority and creation time
        """
        try:
            query = """
                SELECT * FROM transcription_jobs
                WHERE status IN (0, 2)
                ORDER BY priority ASC, created_at ASC
            """

            cursor = self.conn.execute(query)
            rows = cursor.fetchall()

            jobs = []
            for row in rows:
                job = dict(row)
                if job.get('settings_json'):
                    job['settings'] = json.loads(job['settings_json'])
                else:
                    job['settings'] = {}
                jobs.append(job)

            logger.info(f"Retrieved {len(jobs)} pending jobs")
            return jobs

        except sqlite3.Error as e:
            logger.error(f"Error getting pending jobs: {e}")
            raise RuntimeError(f"Failed to get pending jobs: {e}")

    def add_transcription_chunk(
        self,
        job_id: str,
        chunk_index: int,
        text: str,
        start_time: float,
        end_time: float
    ) -> int:
        """
        Add or update a transcription chunk.

        Args:
            job_id: Job ID this chunk belongs to
            chunk_index: Index of this chunk
            text: Transcribed text for this chunk
            start_time: Start time in audio (seconds)
            end_time: End time in audio (seconds)

        Returns:
            Chunk row ID
        """
        try:
            query = """
                INSERT OR REPLACE INTO transcription_chunks
                (job_id, chunk_index, text, start_time, end_time)
                VALUES (?, ?, ?, ?, ?)
            """

            cursor = self.conn.execute(query, (job_id, chunk_index, text, start_time, end_time))
            self.conn.commit()

            logger.debug(f"Added chunk {chunk_index} for job {job_id}")
            return cursor.lastrowid

        except sqlite3.Error as e:
            logger.error(f"Error adding chunk: {e}")
            raise RuntimeError(f"Failed to add chunk: {e}")

    def get_job_chunks(self, job_id: str) -> List[Dict[str, Any]]:
        """
        Get all chunks for a job, ordered by chunk index.

        Args:
            job_id: Job ID to get chunks for

        Returns:
            List of chunk dictionaries
        """
        try:
            query = """
                SELECT chunk_index, text, start_time, end_time, created_at
                FROM transcription_chunks
                WHERE job_id = ?
                ORDER BY chunk_index ASC
            """

            cursor = self.conn.execute(query, (job_id,))
            rows = cursor.fetchall()

            chunks = [dict(row) for row in rows]
            logger.debug(f"Retrieved {len(chunks)} chunks for job {job_id}")
            return chunks

        except sqlite3.Error as e:
            logger.error(f"Error getting chunks: {e}")
            raise RuntimeError(f"Failed to get chunks: {e}")

    def delete_job(self, job_id: str) -> None:
        """
        Delete a job and all its chunks.

        Args:
            job_id: Job ID to delete
        """
        try:
            # Delete chunks first (foreign key constraint)
            self.conn.execute("DELETE FROM transcription_chunks WHERE job_id = ?", (job_id,))

            # Delete job
            self.conn.execute("DELETE FROM transcription_jobs WHERE id = ?", (job_id,))

            self.conn.commit()
            logger.info(f"Deleted job {job_id} and its chunks")

        except sqlite3.Error as e:
            logger.error(f"Error deleting job: {e}")
            raise RuntimeError(f"Failed to delete job: {e}")

    def cleanup_old_jobs(self, days: int = 30) -> int:
        """
        Delete completed/failed jobs older than specified days.

        Args:
            days: Number of days to keep

        Returns:
            Number of jobs deleted
        """
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            cutoff_str = cutoff_date.strftime('%Y-%m-%d %H:%M:%S')

            # Get job IDs to delete
            cursor = self.conn.execute("""
                SELECT id FROM transcription_jobs
                WHERE status IN (3, 4, 5)
                AND completed_at < ?
            """, (cutoff_str,))

            job_ids = [row[0] for row in cursor.fetchall()]

            if not job_ids:
                logger.info("No old jobs to clean up")
                return 0

            # Delete chunks for these jobs
            placeholders = ','.join('?' * len(job_ids))
            self.conn.execute(
                f"DELETE FROM transcription_chunks WHERE job_id IN ({placeholders})",
                job_ids
            )

            # Delete jobs
            self.conn.execute(
                f"DELETE FROM transcription_jobs WHERE id IN ({placeholders})",
                job_ids
            )

            self.conn.commit()
            logger.info(f"Cleaned up {len(job_ids)} old jobs")
            return len(job_ids)

        except sqlite3.Error as e:
            logger.error(f"Error cleaning up jobs: {e}")
            raise RuntimeError(f"Failed to cleanup jobs: {e}")

    # ==================== End of Job Management Methods ====================

    def close(self) -> None:
        """Close database connection"""
        if self.conn:
            self.conn.close()
            logger.info("Database connection closed")
