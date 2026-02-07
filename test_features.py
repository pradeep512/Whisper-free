#!/usr/bin/env python3
"""
Test script to verify all implemented features without GUI
Tests: Database, Queue Manager, File Loading, Error Handling
"""

import sys
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_database():
    """Test database operations and pagination"""
    logger.info("=" * 60)
    logger.info("TEST 1: Database Operations & Pagination")
    logger.info("=" * 60)

    try:
        from app.data.database import DatabaseManager

        # Cleanup old test database
        Path("test_history.db").unlink(missing_ok=True)

        # Create test database
        db = DatabaseManager("test_history.db")

        # Test 1: Add transcriptions
        logger.info("Adding test transcriptions...")
        for i in range(15):
            db.add_transcription(
                text=f"Test transcription {i+1}",
                language="en",
                duration=5.0,
                model_used="small",
                source_type="microphone" if i % 2 == 0 else "file"
            )
        logger.info("✅ Added 15 transcriptions (8 microphone, 7 file)")

        # Test 2: Get total count
        total = db.get_transcription_count()
        logger.info(f"✅ Total transcriptions: {total}")
        assert total == 15, f"Expected 15, got {total}"

        # Test 3: Pagination - Page 1
        page1 = db.get_recent_transcriptions(limit=5, offset=0)
        logger.info(f"✅ Page 1: {len(page1)} entries")
        assert len(page1) == 5, f"Expected 5, got {len(page1)}"

        # Test 4: Pagination - Page 2
        page2 = db.get_recent_transcriptions(limit=5, offset=5)
        logger.info(f"✅ Page 2: {len(page2)} entries")
        assert len(page2) == 5, f"Expected 5, got {len(page2)}"

        # Test 5: Check source_type field
        for item in page1:
            assert 'source_type' in item, "source_type field missing"
        logger.info("✅ All entries have source_type field")

        # Test 6: Add transcription job
        logger.info("Testing job persistence...")
        job_id = db.add_transcription_job(
            job_id="test-job-123",
            priority=1,
            status=0,  # PENDING
            file_path="/test/audio.mp3",
            language="en",
            settings={'beam_size': 1, 'temperature': 0.0}
        )
        logger.info(f"✅ Created job: {job_id}")

        # Test 7: Update job
        db.update_transcription_job(
            job_id=job_id,
            status=1,  # RUNNING
            current_chunk_index=5,
            completed_chunks=5
        )
        logger.info("✅ Updated job status and progress")

        # Test 8: Retrieve job
        job = db.get_transcription_job(job_id)
        assert job is not None, "Failed to retrieve job"
        assert job['status'] == 1, f"Expected status 1, got {job['status']}"
        assert job['completed_chunks'] == 5, f"Expected 5 chunks, got {job['completed_chunks']}"
        logger.info(f"✅ Retrieved job: status={job['status']}, chunks={job['completed_chunks']}")

        # Test 9: Add transcription chunk
        db.add_transcription_chunk(
            job_id=job_id,
            chunk_index=0,
            text="Test chunk 0",
            start_time=0.0,
            end_time=30.0
        )
        logger.info("✅ Added transcription chunk")

        # Test 10: Get job chunks
        chunks = db.get_job_chunks(job_id)
        assert len(chunks) == 1, f"Expected 1 chunk, got {len(chunks)}"
        logger.info(f"✅ Retrieved {len(chunks)} chunk(s)")

        # Cleanup
        db.close()
        Path("test_history.db").unlink(missing_ok=True)

        logger.info("✅ DATABASE TEST PASSED")
        return True

    except Exception as e:
        logger.error(f"❌ DATABASE TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_queue_manager_imports():
    """Test that queue manager can be imported and initialized"""
    logger.info("=" * 60)
    logger.info("TEST 2: TranscriptionQueueManager Import")
    logger.info("=" * 60)

    try:
        from app.core.transcription_queue_manager import (
            TranscriptionQueueManager, JobPriority, JobStatus, TranscriptionJob
        )

        logger.info("✅ Imported TranscriptionQueueManager")
        logger.info("✅ Imported JobPriority enum")
        logger.info("✅ Imported JobStatus enum")
        logger.info("✅ Imported TranscriptionJob dataclass")

        # Test enums - JobPriority uses Enum with explicit values
        assert JobPriority.HIGH.value == 0, "HIGH priority value should be 0"
        assert JobPriority.NORMAL.value == 1, "NORMAL priority value should be 1"
        assert JobPriority.LOW.value == 2, "LOW priority value should be 2"
        logger.info("✅ JobPriority values correct (HIGH=0, NORMAL=1, LOW=2)")

        # JobStatus uses auto() which starts from 1
        assert hasattr(JobStatus, 'PENDING'), "JobStatus should have PENDING"
        assert hasattr(JobStatus, 'RUNNING'), "JobStatus should have RUNNING"
        assert hasattr(JobStatus, 'COMPLETED'), "JobStatus should have COMPLETED"
        assert hasattr(JobStatus, 'FAILED'), "JobStatus should have FAILED"
        assert hasattr(JobStatus, 'CANCELLED'), "JobStatus should have CANCELLED"
        assert hasattr(JobStatus, 'PAUSED'), "JobStatus should have PAUSED"
        logger.info("✅ JobStatus has all required states")

        logger.info("✅ QUEUE MANAGER IMPORT TEST PASSED")
        return True

    except Exception as e:
        logger.error(f"❌ QUEUE MANAGER IMPORT TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_ui_imports():
    """Test that UI components can be imported"""
    logger.info("=" * 60)
    logger.info("TEST 3: UI Component Imports")
    logger.info("=" * 60)

    try:
        # Test batch panel import
        from app.ui.batch_transcribe_panel import BatchTranscribePanel, FileStatus
        logger.info("✅ Imported BatchTranscribePanel")

        # Check FileStatus constants
        assert hasattr(FileStatus, 'PENDING'), "FileStatus.PENDING missing"
        assert hasattr(FileStatus, 'RUNNING'), "FileStatus.RUNNING missing"
        assert hasattr(FileStatus, 'COMPLETED'), "FileStatus.COMPLETED missing"
        assert hasattr(FileStatus, 'FAILED'), "FileStatus.FAILED missing"
        logger.info("✅ FileStatus constants present")

        # Test history panel import
        from app.ui.history_panel import HistoryPanel
        logger.info("✅ Imported HistoryPanel")

        # Test file transcribe panel import
        from app.ui.file_transcribe_panel import FileTranscribePanel
        logger.info("✅ Imported FileTranscribePanel")

        # Test main window import
        from app.ui.main_window import MainWindow
        logger.info("✅ Imported MainWindow")

        logger.info("✅ UI COMPONENT IMPORT TEST PASSED")
        return True

    except Exception as e:
        logger.error(f"❌ UI COMPONENT IMPORT TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_audio_file_loader():
    """Test audio file loader validation"""
    logger.info("=" * 60)
    logger.info("TEST 4: Audio File Loader")
    logger.info("=" * 60)

    try:
        from app.core.audio_file_loader import AudioFileLoader

        # Test supported formats
        logger.info(f"Supported formats: {AudioFileLoader.SUPPORTED_FORMATS}")
        assert '.mp3' in AudioFileLoader.SUPPORTED_FORMATS, ".mp3 should be supported"
        assert '.wav' in AudioFileLoader.SUPPORTED_FORMATS, ".wav should be supported"
        logger.info("✅ Expected formats are supported")

        # Test validation with non-existent file
        is_valid, error_msg = AudioFileLoader.validate_file("/nonexistent/file.mp3")
        assert not is_valid, "Non-existent file should be invalid"
        assert "does not exist" in error_msg.lower(), "Error message should mention file doesn't exist"
        logger.info(f"✅ Non-existent file validation: {error_msg}")

        # Test validation with invalid extension
        is_valid, error_msg = AudioFileLoader.validate_file("/tmp/test.xyz")
        assert not is_valid, "Unsupported extension should be invalid"
        logger.info(f"✅ Invalid extension validation: {error_msg}")

        logger.info("✅ AUDIO FILE LOADER TEST PASSED")
        return True

    except Exception as e:
        logger.error(f"❌ AUDIO FILE LOADER TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_error_handling():
    """Test error handling in batch panel"""
    logger.info("=" * 60)
    logger.info("TEST 5: Error Handling Features")
    logger.info("=" * 60)

    try:
        from app.ui.batch_transcribe_panel import BatchTranscribePanel

        # Check that _show_error_details method exists
        assert hasattr(BatchTranscribePanel, '_show_error_details'), \
            "BatchTranscribePanel should have _show_error_details method"
        logger.info("✅ Error details method exists")

        # Check that error_messages dict is initialized
        # We'll check this by looking at __init__
        import inspect
        init_source = inspect.getsource(BatchTranscribePanel.__init__)
        assert 'error_messages' in init_source, "error_messages should be initialized"
        logger.info("✅ Error messages storage initialized")

        logger.info("✅ ERROR HANDLING TEST PASSED")
        return True

    except Exception as e:
        logger.error(f"❌ ERROR HANDLING TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_config():
    """Test configuration manager"""
    logger.info("=" * 60)
    logger.info("TEST 6: Configuration Manager")
    logger.info("=" * 60)

    try:
        from app.data.config import ConfigManager

        # Create test config
        config = ConfigManager("test_config.yaml")

        # Test set and get
        config.set('test.key', 'test_value')
        value = config.get('test.key')
        assert value == 'test_value', f"Expected 'test_value', got '{value}'"
        logger.info("✅ Config set/get works")

        # Test default value
        default = config.get('nonexistent.key', 'default')
        assert default == 'default', f"Expected 'default', got '{default}'"
        logger.info("✅ Config default value works")

        # Cleanup
        Path("test_config.yaml").unlink(missing_ok=True)

        logger.info("✅ CONFIGURATION TEST PASSED")
        return True

    except Exception as e:
        logger.error(f"❌ CONFIGURATION TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests"""
    logger.info("\n" + "=" * 60)
    logger.info("WHISPER-FREE FEATURE VERIFICATION")
    logger.info("Testing all implemented features without GUI")
    logger.info("=" * 60 + "\n")

    results = []

    # Run tests
    results.append(("Database & Pagination", test_database()))
    results.append(("Queue Manager Import", test_queue_manager_imports()))
    results.append(("UI Component Imports", test_ui_imports()))
    results.append(("Audio File Loader", test_audio_file_loader()))
    results.append(("Error Handling", test_error_handling()))
    results.append(("Configuration", test_config()))

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("TEST SUMMARY")
    logger.info("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        logger.info(f"{test_name:.<40} {status}")

    logger.info("=" * 60)
    logger.info(f"TOTAL: {passed}/{total} tests passed")
    logger.info("=" * 60)

    if passed == total:
        logger.info("\n🎉 ALL TESTS PASSED! 🎉\n")
        return 0
    else:
        logger.info(f"\n⚠️  {total - passed} TEST(S) FAILED\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
