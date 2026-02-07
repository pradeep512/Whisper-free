#!/usr/bin/env python3
"""
Demo script for Whisper-Free UI components

This script demonstrates the main UI components without requiring
the full Whisper engine or GPU. It's useful for testing the UI
independently.

Usage:
    python demo_ui.py

Requirements:
    - PySide6
    - All dependencies from requirements.txt
"""

import sys
from pathlib import Path

# Add app directory to path
sys.path.insert(0, str(Path(__file__).parent))

from PySide6.QtWidgets import QApplication

from app.ui.main_window import MainWindow
from app.data.database import DatabaseManager
from app.data.config import ConfigManager


def populate_demo_data(db: DatabaseManager):
    """Add some demo transcriptions to the database"""
    demo_transcriptions = [
        ("Hello world, this is a test transcription.", "en", 2.5, "small"),
        ("Python is a great programming language.", "en", 3.2, "small"),
        ("Bonjour, comment allez-vous?", "fr", 2.8, "small"),
        ("Machine learning is fascinating.", "en", 4.1, "medium"),
        ("The quick brown fox jumps over the lazy dog.", "en", 3.5, "small"),
        ("Artificial intelligence is the future.", "en", 3.8, "small"),
        ("Buenos días, ¿cómo estás?", "es", 2.3, "small"),
        ("Deep learning requires lots of data.", "en", 3.9, "medium"),
        ("Whisper is an amazing transcription model.", "en", 4.2, "small"),
        ("This is the last demo transcription.", "en", 2.9, "small"),
    ]

    for text, lang, duration, model in demo_transcriptions:
        db.add_transcription(text, lang, duration, model)

    print(f"Added {len(demo_transcriptions)} demo transcriptions")


def main():
    """Main entry point for demo"""
    # Create Qt application
    app = QApplication(sys.argv)
    app.setApplicationName("Whisper-Free Demo")

    # Create database and config
    db_path = Path.home() / ".config" / "whisper-free" / "demo_history.db"
    config_path = Path.home() / ".config" / "whisper-free" / "demo_config.yaml"

    print(f"Database: {db_path}")
    print(f"Config: {config_path}")

    # Initialize managers
    db = DatabaseManager(str(db_path))
    config = ConfigManager(str(config_path))

    # Populate with demo data if empty
    stats = db.get_stats()
    if stats['total_count'] == 0:
        print("Database is empty, adding demo data...")
        populate_demo_data(db)
    else:
        print(f"Database has {stats['total_count']} existing transcriptions")

    # Create main window
    window = MainWindow(db, config)

    # Show window
    window.show()

    # Update status
    window.update_status("Ready")
    window.update_vram_usage(1536)  # 1.5 GB

    print("\n" + "=" * 60)
    print("Whisper-Free UI Demo")
    print("=" * 60)
    print("\nFeatures to try:")
    print("  1. Navigate between History, Settings, and About panels")
    print("  2. Search for transcriptions in the history")
    print("  3. Click 'Copy' button to copy text to clipboard")
    print("  4. Export history to TXT or JSON")
    print("  5. Modify settings and click 'Save Settings'")
    print("  6. Try 'Reset to Defaults' in settings")
    print("\nNote: This is a UI-only demo. Actual transcription requires")
    print("      the full application with WhisperEngine.")
    print("=" * 60 + "\n")

    # Run application
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
