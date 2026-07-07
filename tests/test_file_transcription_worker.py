"""End-to-end test of the file/batch transcription path on Windows.

#14's acceptance criteria include "selecting an audio file transcribes
correctly" and "batch transcription of multiple files works", but those were
only verified manually via the GUI panels (file_transcribe_panel.py,
batch_transcribe_panel.py) which need an interactive session. This test
drives the same worker those panels use (FileTranscriptionWorker.run()),
directly against WhisperEngineFasterWhisper and the real speech fixture, to
give that acceptance criterion automated coverage without a GUI.

Requires network access on first run (downloads the `tiny` CTranslate2
checkpoint, cached under HF_HOME after that) - same as
test_faster_whisper_engine.py.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

faster_whisper = pytest.importorskip("faster_whisper")
librosa = pytest.importorskip("librosa")

from app.core.file_transcription_worker import FileTranscriptionWorker
from app.core.whisper_engine_faster_whisper import WhisperEngineFasterWhisper
from app.data.config import ConfigManager

FIXTURE = Path(__file__).parent / "fixtures" / "hello_test.wav"


@pytest.fixture(scope="module")
def tiny_engine():
    engine = WhisperEngineFasterWhisper(model_name="tiny", device="cpu")
    yield engine
    engine.cleanup()


@pytest.fixture
def config(tmp_path):
    return ConfigManager(config_path=str(tmp_path / "config.yaml"))


def _run_worker(audio_path: Path, engine, config):
    worker = FileTranscriptionWorker(str(audio_path), engine, config)
    results = []
    failures = []
    worker.transcription_complete.connect(results.append)
    worker.transcription_failed.connect(failures.append)
    worker.run()
    assert not failures, f"transcription failed: {failures}"
    assert len(results) == 1
    return results[0]


def test_single_file_transcription_writes_txt(tmp_path, tiny_engine, config):
    audio_path = tmp_path / "hello_test.wav"
    shutil.copyfile(FIXTURE, audio_path)

    result = _run_worker(audio_path, tiny_engine, config)

    assert "test" in result["text"].lower()
    assert result["language"] == "en"
    assert result["audio_file"] == str(audio_path)

    output_path = Path(result["output_path"])
    assert output_path.exists()
    assert output_path.suffix == ".txt"
    assert "test" in output_path.read_text(encoding="utf-8").lower()


def test_batch_transcription_of_multiple_files(tmp_path, tiny_engine, config):
    audio_paths = []
    for i in range(2):
        audio_path = tmp_path / f"hello_test_{i}.wav"
        shutil.copyfile(FIXTURE, audio_path)
        audio_paths.append(audio_path)

    results = [_run_worker(p, tiny_engine, config) for p in audio_paths]

    assert len(results) == 2
    for audio_path, result in zip(audio_paths, results):
        assert result["audio_file"] == str(audio_path)
        assert Path(result["output_path"]).exists()


@pytest.mark.skipif(
    shutil.which("ffmpeg") is None,
    reason="requires ffmpeg on PATH to synthesize the .mp4 fixture and to "
    "decode it via VideoAudioExtractor (see docs/adr/0002-video-decode-via-ffmpeg.md)",
)
def test_single_video_file_transcription_writes_txt(tmp_path, tiny_engine, config):
    """#25: a single video Media file transcribes end-to-end.

    Synthesizes a ~2s .mp4 (video + the speech fixture's audio track) with
    ffmpeg, then drives the same FileTranscriptionWorker seam used by the
    audio tests above. Asserts a non-empty Transcription is produced and
    written next to the source, exactly as for an audio Media file.
    """
    video_path = tmp_path / "hello_test.mp4"

    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "color=c=black:s=64x64:d=2",
            "-i", str(FIXTURE),
            "-shortest",
            "-c:v", "libx264", "-c:a", "aac",
            str(video_path),
        ],
        check=True,
        capture_output=True,
    )

    result = _run_worker(video_path, tiny_engine, config)

    assert "test" in result["text"].lower()
    assert result["audio_file"] == str(video_path)

    output_path = Path(result["output_path"])
    assert output_path.exists()
    assert output_path.suffix == ".txt"
    assert "test" in output_path.read_text(encoding="utf-8").lower()
