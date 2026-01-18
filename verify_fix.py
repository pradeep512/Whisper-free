
import sys
import os
from pathlib import Path
import logging

# Add current directory to path
sys.path.append(os.getcwd())

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("verifier")

def verify_imports():
    logger.info("Verifying imports...")
    try:
        from app.main import WhisperFreeApp, TranscriptionWorker
        logger.info("✔ Imported WhisperFreeApp and TranscriptionWorker")
    except ImportError as e:
        logger.error(f"❌ Failed to import main app components: {e}")
        return False
    
    try:
        from app.ui.overlay import DynamicIslandOverlay
        logger.info("✔ Imported DynamicIslandOverlay")
    except ImportError as e:
        logger.error(f"❌ Failed to import overlay: {e}")
        return False

    return True

def verify_classes():
    logger.info("Verifying classes...")
    
    # 1. Check TranscriptionWorker signals
    from app.main import TranscriptionWorker
    if not hasattr(TranscriptionWorker, 'finished'):
        logger.error("❌ TranscriptionWorker missing 'finished' signal")
        return False
    if not hasattr(TranscriptionWorker, 'error'):
        logger.error("❌ TranscriptionWorker missing 'error' signal")
        return False
    logger.info("✔ TranscriptionWorker structure ok")

    # 2. Check Overlay methods
    from app.ui.overlay import DynamicIslandOverlay
    if not hasattr(DynamicIslandOverlay, 'set_position'):
        logger.error("❌ DynamicIslandOverlay missing 'set_position'")
        return False
    if not hasattr(DynamicIslandOverlay, '_calculate_geometry'):
        logger.error("❌ DynamicIslandOverlay missing '_calculate_geometry'")
        return False
    logger.info("✔ DynamicIslandOverlay structure ok")
    
    # 3. Check WhisperEngine kwargs
    from app.core.whisper_engine import WhisperEngine
    import inspect
    sig = inspect.signature(WhisperEngine.transcribe)
    if 'kwargs' not in str(sig) and '**' not in str(sig):
         # It might be in **kwargs
         pass
         # Actually inspect parameters
    params = sig.parameters
    if 'kwargs' in params or any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()):
        logger.info("✔ WhisperEngine.transcribe accepts kwargs")
    else:
        logger.error("❌ WhisperEngine.transcribe does NOT accept kwargs")
        return False

    return True

if __name__ == "__main__":
    logger.info("Starting verification...")
    if verify_imports() and verify_classes():
        logger.info("ALL CHECKS PASSED")
        sys.exit(0)
    else:
        logger.error("VERIFICATION FAILED")
        sys.exit(1)
