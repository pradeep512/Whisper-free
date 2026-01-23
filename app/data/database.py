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
            check_same_thread=False  # Allow multi-threaded access for Qt
        )
        self.conn.row_factory = sqlite3.Row  # Enable column access by name

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
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO transcriptions
                (text, language, duration, model_used, audio_path, source_type, output_path)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (text.strip(), language, duration, model_used, audio_path, source_type, output_path))

            self.conn.commit()
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

    def get_recent_transcriptions(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get recent transcriptions ordered by timestamp.

        Args:
            limit: Maximum number of results

        Returns:
            List of dicts with keys:
                - id: int
                - timestamp: str (formatted like "Today at 2:34 PM")
                - text: str
                - language: str
                - duration: float
                - model_used: str
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT id, timestamp, text, language, duration, model_used
                FROM transcriptions
                ORDER BY timestamp DESC, id DESC
                LIMIT ?
            """, (limit,))

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

            logger.debug(f"Retrieved {len(results)} recent transcriptions")
            return results

        except sqlite3.Error as e:
            logger.error(f"Error getting recent transcriptions: {e}")
            raise RuntimeError(f"Failed to get recent transcriptions: {e}")

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

    def close(self) -> None:
        """Close database connection"""
        if self.conn:
            self.conn.close()
            logger.info("Database connection closed")
