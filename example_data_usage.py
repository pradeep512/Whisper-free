#!/usr/bin/env python3
"""
Example demonstrating real-world usage of DatabaseManager and ConfigManager

This script shows how the data components would be used in the main application.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from app.data import DatabaseManager, ConfigManager


def main():
    print("=" * 60)
    print("Whisper-Free Data Components - Usage Example")
    print("=" * 60)

    # =================================================================
    # 1. INITIALIZATION
    # =================================================================
    print("\n1. Initializing components...")

    # Load configuration
    config = ConfigManager()
    print(f"   ✓ Config loaded from: {config.config_path}")

    # Initialize database using config path
    db = DatabaseManager(db_path=config.get('storage.database_path'))
    print(f"   ✓ Database initialized at: {db.db_path}")

    # =================================================================
    # 2. CONFIGURATION USAGE
    # =================================================================
    print("\n2. Using configuration...")

    # Get Whisper settings
    model = config.get('whisper.model')
    device = config.get('whisper.device')
    language = config.get('whisper.language', 'auto-detect')
    print(f"   Whisper model: {model}")
    print(f"   Device: {device}")
    print(f"   Language: {language}")

    # Get UI settings
    theme = config.get('ui.theme')
    history_limit = config.get('ui.history_limit')
    print(f"   UI theme: {theme}")
    print(f"   History limit: {history_limit}")

    # Get hotkey
    hotkey = config.get('hotkey.primary')
    print(f"   Primary hotkey: {hotkey}")

    # =================================================================
    # 3. ADDING TRANSCRIPTIONS
    # =================================================================
    print("\n3. Adding sample transcriptions...")

    sample_transcriptions = [
        ("Hello world, this is a test.", "en", 2.5),
        ("Testing voice recognition system.", "en", 3.1),
        ("How are you doing today?", "en", 2.8),
        ("The quick brown fox jumps over the lazy dog.", "en", 4.2),
        ("Python is a great programming language.", "en", 3.7),
    ]

    for text, lang, duration in sample_transcriptions:
        db.add_transcription(
            text=text,
            language=lang,
            duration=duration,
            model_used=model
        )

    print(f"   ✓ Added {len(sample_transcriptions)} transcriptions")

    # =================================================================
    # 4. RETRIEVING HISTORY
    # =================================================================
    print("\n4. Retrieving transcription history...")

    history = db.get_recent_transcriptions(limit=history_limit)
    print(f"   Retrieved {len(history)} recent transcriptions:")

    for i, item in enumerate(history[:3], 1):
        print(f"   {i}. [{item['timestamp']}] {item['text'][:50]}...")

    # =================================================================
    # 5. SEARCHING
    # =================================================================
    print("\n5. Searching transcriptions...")

    search_query = "test"
    results = db.search_transcriptions(search_query)
    print(f"   Search for '{search_query}': {len(results)} results")

    for item in results:
        print(f"   - {item['text']}")

    # =================================================================
    # 6. STATISTICS
    # =================================================================
    print("\n6. Database statistics...")

    stats = db.get_stats()
    print(f"   Total transcriptions: {stats['total_count']}")
    print(f"   Total audio duration: {stats['total_duration']:.1f} seconds")
    print(f"   Languages: {stats['languages']}")

    if stats['oldest_date'] and stats['newest_date']:
        print(f"   Date range: {stats['oldest_date']} to {stats['newest_date']}")

    # =================================================================
    # 7. EXPORT
    # =================================================================
    print("\n7. Exporting transcriptions...")

    # Export to TXT
    txt_path = "/tmp/whisper_transcriptions.txt"
    db.export_to_txt(txt_path)
    txt_size = Path(txt_path).stat().st_size
    print(f"   ✓ Exported to TXT: {txt_path} ({txt_size} bytes)")

    # Export to JSON
    json_path = "/tmp/whisper_transcriptions.json"
    db.export_to_json(json_path)
    json_size = Path(json_path).stat().st_size
    print(f"   ✓ Exported to JSON: {json_path} ({json_size} bytes)")

    # =================================================================
    # 8. CONFIGURATION CHANGES
    # =================================================================
    print("\n8. Updating configuration...")

    # Change model
    old_model = config.get('whisper.model')
    config.set('whisper.model', 'medium')
    print(f"   Changed model: {old_model} → medium")

    # Validate changes
    errors = config.validate()
    if errors:
        print("   ⚠ Validation errors:")
        for error in errors:
            print(f"     - {error}")
    else:
        print("   ✓ Configuration is valid")
        # In real app, you would call config.save() here
        # config.save()

    # Restore original value (don't actually save changes)
    config.set('whisper.model', old_model)

    # =================================================================
    # 9. CLEANUP SIMULATION
    # =================================================================
    print("\n9. Cleanup simulation...")

    retention_days = config.get('storage.retention_days')
    print(f"   Retention policy: {retention_days} days")

    # In real app, you would run this on startup:
    # deleted = db.cleanup_old(days=retention_days)
    # print(f"   Deleted {deleted} old transcriptions")
    print("   (Skipping actual cleanup for demo)")

    # =================================================================
    # 10. VALIDATION EXAMPLE
    # =================================================================
    print("\n10. Configuration validation example...")

    # Show what happens with invalid config
    config_copy = ConfigManager()
    config_copy.set('whisper.model', 'invalid_model')
    config_copy.set('audio.sample_rate', 44100)  # Should be 16000
    config_copy.set('ui.history_limit', -10)  # Should be positive

    errors = config_copy.validate()
    print(f"   Validation found {len(errors)} errors:")
    for error in errors[:3]:  # Show first 3
        print(f"     - {error}")

    # =================================================================
    # CLEANUP
    # =================================================================
    print("\n" + "=" * 60)
    db.close()
    print("✅ Example completed successfully!")
    print("=" * 60)

    print("\nSummary:")
    print(f"  - Configuration: {config.config_path}")
    print(f"  - Database: {db.db_path}")
    print(f"  - Transcriptions: {stats['total_count']}")
    print(f"  - Exports: {txt_path}, {json_path}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
