"""Integration test for WhisperEngineFasterWhisper against a real audio fixture.

tests/fixtures/hello_test.wav is real synthesized speech (Windows SAPI,
"This is a test of Whisper Free transcription on Windows."), not silence or a
tone — so a non-empty, roughly-matching transcript is a meaningful signal
that the faster-whisper backend actually works end-to-end, not just that it
returns the right dict shape.

Requires network access on first run (downloads the `tiny` CTranslate2
checkpoint from the HuggingFace Hub, cached under HF_HOME after that).
"""
from pathlib import Path

import numpy as np
import pytest

faster_whisper = pytest.importorskip("faster_whisper")
librosa = pytest.importorskip("librosa")

from app.core.whisper_engine_faster_whisper import WhisperEngineFasterWhisper

FIXTURE = Path(__file__).parent / "fixtures" / "hello_test.wav"


@pytest.fixture(scope="module")
def tiny_engine():
    engine = WhisperEngineFasterWhisper(model_name="tiny", device="cpu")
    yield engine
    engine.cleanup()


def test_transcribe_returns_expected_shape_and_nonempty_text(tiny_engine):
    audio, sr = librosa.load(str(FIXTURE), sr=16000, mono=True)
    audio = audio.astype(np.float32)

    result = tiny_engine.transcribe(audio, language="en")

    assert isinstance(result["text"], str)
    assert result["text"].strip() != ""
    assert "test" in result["text"].lower()
    assert result["language"] == "en"
    assert isinstance(result["segments"], list)
    assert len(result["segments"]) >= 1
    assert "end" in result["segments"][0]
    assert result["duration"] > 0
