
import sys
import os
import logging

# Add current directory to path
sys.path.append(os.getcwd())

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("verifier")

def verify_structure():
    logger.info("Verifying structural changes...")
    
    try:
        from app.main import WhisperFreeApp, StartRecordingWorker
        
        # Check StartRecordingWorker
        if not hasattr(StartRecordingWorker, 'finished') or not hasattr(StartRecordingWorker, 'error'):
            logger.error("❌ StartRecordingWorker missing signals")
            return False
        logger.info("✔ StartRecordingWorker class structure ok")

        # Check WhisperFreeApp methods
        needed_methods = ['start_recording', 'on_recording_started', 'on_recording_error']
        for method in needed_methods:
            if not hasattr(WhisperFreeApp, method):
                logger.error(f"❌ WhisperFreeApp missing method: {method}")
                return False
        logger.info("✔ WhisperFreeApp methods ok")
        
        # Check signal definition
        if not hasattr(WhisperFreeApp, 'start_recording_signal'):
             logger.error("❌ WhisperFreeApp missing start_recording_signal")
             return False
        logger.info("✔ WhisperFreeApp signals ok")

        return True

    except ImportError as e:
        logger.error(f"❌ Import failed: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Verification error: {e}")
        return False

if __name__ == "__main__":
    if verify_structure():
        logger.info("ALL CHECKS PASSED")
        sys.exit(0)
    else:
        logger.error("VERIFICATION FAILED")
        sys.exit(1)
