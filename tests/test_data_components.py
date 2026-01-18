#!/usr/bin/env python3
"""Test DatabaseManager and ConfigManager"""
import os
import sys
import tempfile
from pathlib import Path
import json

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.data.database import DatabaseManager
from app.data.config import ConfigManager


def test_config_manager():
    """Test configuration management"""
    print("=== Testing ConfigManager ===")

    # Create temp config
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.yaml"
        config = ConfigManager(config_path=str(config_path))

        # Test get
        assert config.get('whisper.model') == 'small', "Default model wrong"
        print("  ✓ Default config loaded")

        # Test set
        config.set('whisper.model', 'medium')
        assert config.get('whisper.model') == 'medium', "Set failed"
        print("  ✓ Set value works")

        # Test save/load
        config.save()
        config2 = ConfigManager(config_path=str(config_path))
        assert config2.get('whisper.model') == 'medium', "Save/load failed"
        print("  ✓ Save and load works")

        # Test validation
        config.set('whisper.model', 'invalid_model')
        errors = config.validate()
        assert len(errors) > 0, "Validation should catch invalid model"
        print("  ✓ Validation works")

        # Test reset
        config.reset_to_defaults()
        assert config.get('whisper.model') == 'small', "Reset failed"
        print("  ✓ Reset to defaults works")

        # Test nested get/set
        config.set('app.autostart', True)
        assert config.get('app.autostart') is True, "Nested set failed"
        print("  ✓ Nested get/set works")

        # Test default value
        assert config.get('nonexistent.key', 'default_val') == 'default_val', "Default value failed"
        print("  ✓ Default values work")

        # Test get_all
        all_config = config.get_all()
        assert 'whisper' in all_config, "get_all missing keys"
        assert all_config['whisper']['model'] == 'small', "get_all wrong value"
        print("  ✓ get_all works")

    print("  ✅ All ConfigManager tests passed!\n")


def test_database_manager():
    """Test database operations"""
    print("=== Testing DatabaseManager ===")

    # Create temp database
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = DatabaseManager(db_path=str(db_path))

        # Test add
        row_id = db.add_transcription(
            text="Test transcription one",
            language="en",
            duration=5.2,
            model_used="small"
        )
        assert row_id == 1, "First row should be ID 1"
        print("  ✓ Add transcription works")

        # Add more
        db.add_transcription("Test transcription two", "en", 3.1, "small")
        db.add_transcription("Another test here", "en", 7.5, "small")

        # Test get recent
        recent = db.get_recent_transcriptions(limit=10)
        assert len(recent) == 3, "Should have 3 transcriptions"
        assert recent[0]['text'] == "Another test here", "Order wrong"
        assert 'timestamp' in recent[0], "Missing timestamp"
        assert recent[0]['id'] == 3, "Wrong ID"
        print("  ✓ Get recent works")

        # Test search
        results = db.search_transcriptions("transcription")
        assert len(results) == 2, f"Should find 2 matches, found {len(results)}"
        print("  ✓ Search works")

        # Test case-insensitive search
        results_upper = db.search_transcriptions("TRANSCRIPTION")
        assert len(results_upper) == 2, "Case-insensitive search failed"
        print("  ✓ Case-insensitive search works")

        # Test export TXT
        txt_path = Path(tmpdir) / "export.txt"
        db.export_to_txt(str(txt_path))
        assert txt_path.exists(), "TXT export failed"
        content = txt_path.read_text()
        assert "Test transcription one" in content, "TXT export missing content"
        print("  ✓ Export to TXT works")

        # Test export JSON
        json_path = Path(tmpdir) / "export.json"
        db.export_to_json(str(json_path))
        assert json_path.exists(), "JSON export failed"
        with open(json_path) as f:
            json_data = json.load(f)
        assert len(json_data) == 3, "JSON export wrong count"
        assert json_data[0]['text'] == "Test transcription one", "JSON export wrong order"
        print("  ✓ Export to JSON works")

        # Test stats
        stats = db.get_stats()
        assert stats['total_count'] == 3, f"Stats count wrong: {stats['total_count']}"
        assert stats['total_duration'] > 0, "Stats duration wrong"
        assert 'en' in stats['languages'], "Stats languages missing 'en'"
        assert stats['languages']['en'] == 3, "Stats language count wrong"
        print("  ✓ Stats work")

        # Test cleanup (should delete nothing since all recent)
        deleted = db.cleanup_old(days=30)
        assert deleted == 0, "Should not delete recent entries"
        print("  ✓ Cleanup (no deletions) works")

        # Test empty text validation
        try:
            db.add_transcription("")
            assert False, "Should raise error for empty text"
        except ValueError:
            print("  ✓ Empty text validation works")

        db.close()
        print("  ✓ Database closes cleanly")

    print("  ✅ All DatabaseManager tests passed!\n")


def test_integration():
    """Test integration between components"""
    print("=== Testing Integration ===")

    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.yaml"
        db_path = Path(tmpdir) / "history.db"

        # Initialize config
        config = ConfigManager(config_path=str(config_path))
        config.set('storage.database_path', str(db_path))
        config.save()

        # Initialize database using config
        db = DatabaseManager(db_path=config.get('storage.database_path'))

        # Add transcription using config values
        model = config.get('whisper.model')
        db.add_transcription(
            text="Integration test transcription",
            language="en",
            duration=4.5,
            model_used=model
        )

        # Verify
        recent = db.get_recent_transcriptions(limit=1)
        assert recent[0]['model_used'] == 'small', "Integration failed"
        print("  ✓ Config + Database integration works")

        db.close()

    print("  ✅ All integration tests passed!\n")


def test_edge_cases():
    """Test edge cases and error handling"""
    print("=== Testing Edge Cases ===")

    with tempfile.TemporaryDirectory() as tmpdir:
        # Test config with missing file
        config_path = Path(tmpdir) / "nonexistent" / "config.yaml"
        config = ConfigManager(config_path=str(config_path))
        assert config.get('whisper.model') == 'small', "Should create default config"
        print("  ✓ Config creates missing file")

        # Test database with nested path
        db_path = Path(tmpdir) / "nested" / "path" / "db.db"
        db = DatabaseManager(db_path=str(db_path))
        assert db_path.exists(), "Should create nested directories"
        db.close()
        print("  ✓ Database creates nested directories")

        # Test search with empty query
        db = DatabaseManager(db_path=str(db_path))
        results = db.search_transcriptions("")
        assert len(results) == 0, "Empty search should return empty list"
        results = db.search_transcriptions("   ")
        assert len(results) == 0, "Whitespace search should return empty list"
        db.close()
        print("  ✓ Empty search handling works")

        # Test config validation with multiple errors
        config.set('whisper.model', 'invalid')
        config.set('audio.sample_rate', 44100)
        config.set('ui.history_limit', -5)
        errors = config.validate()
        assert len(errors) >= 3, f"Should have multiple validation errors, got {len(errors)}"
        print("  ✓ Multiple validation errors detected")

    print("  ✅ All edge case tests passed!\n")


if __name__ == "__main__":
    try:
        test_config_manager()
        test_database_manager()
        test_integration()
        test_edge_cases()
        print("=" * 50)
        print("✅ ALL DATA COMPONENT TESTS PASSED!")
        print("=" * 50)
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
