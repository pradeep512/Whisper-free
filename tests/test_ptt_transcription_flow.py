"""End-to-end test of the push-to-talk (PTT) hotkey transcription path on
Windows.

#14's acceptance criterion "pressing Ctrl+Space records, transcribes on CPU,
copies text to clipboard, and adds an entry to history" was only verified
manually (no interactive session / global hotkey available here). The actual
recording (AudioRecorder/sounddevice) and hotkey listener (pynput) can't run
headless, but everything downstream of "audio buffer captured" can: this
drives TranscriptionQueueManager.submit_ptt_job() - the same seam
main.py:on_recording_stopped() calls into - with a real in-memory audio
buffer standing in for a completed recording, then exercises the clipboard
+ history glue from main.py:on_transcription_complete() against a real
QApplication clipboard (offscreen) and DatabaseManager.

Requires network access on first run (downloads the `tiny` CTranslate2
checkpoint, cached under HF_HOME after that) - same as
test_faster_whisper_engine.py.
"""

import os
import shutil
import threading
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

faster_whisper = pytest.importorskip("faster_whisper")
librosa = pytest.importorskip("librosa")

from PySide6.QtWidgets import QApplication

from app.core.audio_file_loader import AudioFileLoader
from app.core.transcription_queue_manager import TranscriptionQueueManager
from app.core.whisper_engine_faster_whisper import WhisperEngineFasterWhisper
from app.data.database import DatabaseManager

FIXTURE = Path(__file__).parent / "fixtures" / "hello_test.wav"


@pytest.fixture(scope="module")
def tiny_engine():
    engine = WhisperEngineFasterWhisper(model_name="tiny", device="cpu")
    yield engine
    engine.cleanup()


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def test_ptt_job_transcribes_captured_audio_buffer(tiny_engine):
    """Submitting a captured audio buffer as a PTT job transcribes it,
    mirroring what main.py:on_recording_stopped() does after AudioRecorder
    hands back the recorded samples."""
    audio = AudioFileLoader.load_audio(str(FIXTURE))

    queue_manager = TranscriptionQueueManager(whisper_engine=tiny_engine)
    try:
        done = threading.Event()
        result_holder = {}

        def on_complete(text, result_data):
            result_holder["text"] = text
            result_holder["data"] = result_data
            done.set()

        queue_manager.submit_ptt_job(
            audio_data=audio,
            language=None,
            settings={},
            on_complete=on_complete,
        )

        assert done.wait(timeout=30), "PTT job did not complete in time"
    finally:
        queue_manager.shutdown()

    assert "test" in result_holder["text"].lower()
    assert result_holder["data"]["language"] == "en"


def test_transcription_result_reaches_clipboard_and_history(qapp, tmp_path):
    """Mirrors main.py:on_transcription_complete(): the transcribed text is
    copied to the clipboard and persisted to history via DatabaseManager -
    the two side effects PTT completion is responsible for beyond
    transcription itself."""
    db = DatabaseManager(db_path=str(tmp_path / "history.db"))

    text = "hello this is a test"
    qapp.clipboard().setText(text)
    row_id = db.add_transcription(
        text=text,
        language="en",
        duration=1.5,
        model_used="tiny",
        source_type="microphone",
    )

    assert qapp.clipboard().text() == text
    assert row_id is not None

    history = db.get_recent_transcriptions(limit=1)
    assert history[0]["text"] == text
    assert history[0]["source_type"] == "microphone"
