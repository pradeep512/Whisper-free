"""Unit tests for #25: the media loader's video allowlist and the ffmpeg
subprocess extractor that decodes video Media files.

Per docs/adr/0002-video-decode-via-ffmpeg.md, video Media files are decoded
via an explicit `ffmpeg` subprocess to a temporary 16kHz mono WAV, which is
then loaded through the existing fast (soundfile-backed) WAV path and
deleted. These tests mock the subprocess so they run on any machine,
including this dev box where ffmpeg is not on PATH.
"""
import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.core.audio_file_loader import AudioFileLoader, AudioLoadError, VideoAudioExtractor


# ---------------------------------------------------------------------------
# Allowlist: is_supported() / validate_file()
# ---------------------------------------------------------------------------

VIDEO_EXTENSIONS = [
    '.mp4', '.mov', '.mkv', '.avi', '.webm', '.m4v', '.flv', '.wmv',
    '.mpeg', '.mpg', '.ts', '.3gp',
]


@pytest.mark.parametrize("ext", VIDEO_EXTENSIONS)
def test_is_supported_accepts_each_video_extension(ext):
    assert AudioFileLoader.is_supported(f"lecture{ext}") is True


@pytest.mark.parametrize("ext", VIDEO_EXTENSIONS)
def test_validate_file_accepts_each_video_extension(tmp_path, ext):
    video_path = tmp_path / f"lecture{ext}"
    video_path.write_bytes(b"not a real container, just needs bytes")

    is_valid, error_msg = AudioFileLoader.validate_file(str(video_path))

    assert is_valid is True
    assert error_msg == ""


@pytest.mark.parametrize("ext", [".txt", ".pdf", ".exe", ".docx", ".zip"])
def test_validate_file_rejects_non_media_junk(tmp_path, ext):
    junk_path = tmp_path / f"notes{ext}"
    junk_path.write_bytes(b"junk")

    is_valid, error_msg = AudioFileLoader.validate_file(str(junk_path))

    assert is_valid is False
    assert "Unsupported format" in error_msg


def test_is_supported_still_rejects_non_media_extension():
    assert AudioFileLoader.is_supported("document.pdf") is False


def test_existing_audio_formats_still_supported():
    # No regression to the pre-existing audio allowlist.
    for ext in ['.mp3', '.wav', '.m4a', '.flac', '.ogg', '.opus', '.webm']:
        assert AudioFileLoader.is_supported(f"clip{ext}") is True


def test_webm_routes_to_existing_audio_path_not_video_extractor():
    # '.webm' appears in both AUDIO_FORMATS and VIDEO_FORMATS; ADR 0002
    # requires audio formats keep their existing librosa path unchanged.
    assert AudioFileLoader.is_video("clip.webm") is False


@pytest.mark.parametrize("ext", [e for e in VIDEO_EXTENSIONS if e != ".webm"])
def test_is_video_true_for_video_only_extensions(ext):
    assert AudioFileLoader.is_video(f"movie{ext}") is True


def test_is_video_false_for_audio_extension():
    assert AudioFileLoader.is_video("song.mp3") is False


# ---------------------------------------------------------------------------
# VideoAudioExtractor: ffmpeg command + temp-file cleanup
# ---------------------------------------------------------------------------


def _mock_completed_process(returncode=0, stderr=""):
    proc = MagicMock()
    proc.returncode = returncode
    proc.stderr = stderr
    return proc


def test_extract_to_wav_builds_expected_ffmpeg_command(tmp_path, monkeypatch):
    video_path = tmp_path / "input.mp4"
    video_path.write_bytes(b"fake video bytes")

    monkeypatch.setattr(
        "app.core.audio_file_loader.shutil.which", lambda name: r"C:\ffmpeg\ffmpeg.exe"
    )

    captured_cmd = {}

    def fake_run(cmd, capture_output, text):
        captured_cmd["cmd"] = cmd
        # ffmpeg would have written the temp wav; simulate that.
        Path(cmd[-1]).write_bytes(b"RIFF....WAVEfmt ")
        return _mock_completed_process(returncode=0)

    monkeypatch.setattr("app.core.audio_file_loader.subprocess.run", fake_run)

    temp_wav_path = VideoAudioExtractor.extract_to_wav(str(video_path))

    try:
        cmd = captured_cmd["cmd"]
        assert cmd[0] == r"C:\ffmpeg\ffmpeg.exe"
        assert "-i" in cmd
        assert cmd[cmd.index("-i") + 1] == str(video_path)
        assert "-ar" in cmd
        assert cmd[cmd.index("-ar") + 1] == "16000"
        assert "-ac" in cmd
        assert cmd[cmd.index("-ac") + 1] == "1"
        assert cmd[-1] == temp_wav_path
        assert Path(temp_wav_path).suffix == ".wav"
        assert Path(temp_wav_path).exists()
    finally:
        VideoAudioExtractor._safe_remove(temp_wav_path)


def test_extract_to_wav_raises_when_ffmpeg_missing(tmp_path, monkeypatch):
    video_path = tmp_path / "input.mp4"
    video_path.write_bytes(b"fake video bytes")

    monkeypatch.setattr("app.core.audio_file_loader.shutil.which", lambda name: None)

    with pytest.raises(AudioLoadError, match="ffmpeg"):
        VideoAudioExtractor.extract_to_wav(str(video_path))


def test_extract_to_wav_cleans_up_temp_file_on_ffmpeg_failure(tmp_path, monkeypatch):
    video_path = tmp_path / "input.mp4"
    video_path.write_bytes(b"fake video bytes")

    monkeypatch.setattr(
        "app.core.audio_file_loader.shutil.which", lambda name: r"C:\ffmpeg\ffmpeg.exe"
    )

    created_paths = []

    def fake_run(cmd, capture_output, text):
        # Simulate ffmpeg leaving behind an (empty/partial) temp file, then
        # failing.
        created_paths.append(cmd[-1])
        return _mock_completed_process(returncode=1, stderr="ffmpeg: no audio stream found")

    monkeypatch.setattr("app.core.audio_file_loader.subprocess.run", fake_run)

    with pytest.raises(AudioLoadError, match="ffmpeg failed"):
        VideoAudioExtractor.extract_to_wav(str(video_path))

    assert created_paths, "expected ffmpeg to have been invoked"
    assert not Path(created_paths[0]).exists(), "temp file must be cleaned up on failure"


def test_extract_to_wav_cleans_up_temp_file_on_subprocess_exception(tmp_path, monkeypatch):
    video_path = tmp_path / "input.mp4"
    video_path.write_bytes(b"fake video bytes")

    monkeypatch.setattr(
        "app.core.audio_file_loader.shutil.which", lambda name: r"C:\ffmpeg\ffmpeg.exe"
    )

    created_paths = []

    def fake_run(cmd, capture_output, text):
        created_paths.append(cmd[-1])
        raise subprocess.SubprocessError("boom")

    monkeypatch.setattr("app.core.audio_file_loader.subprocess.run", fake_run)

    with pytest.raises(subprocess.SubprocessError):
        VideoAudioExtractor.extract_to_wav(str(video_path))

    assert created_paths
    assert not Path(created_paths[0]).exists(), "temp file must be cleaned up on exception"


def test_extract_and_load_deletes_temp_wav_after_successful_load(tmp_path, monkeypatch):
    video_path = tmp_path / "input.mp4"
    video_path.write_bytes(b"fake video bytes")

    monkeypatch.setattr(
        "app.core.audio_file_loader.shutil.which", lambda name: r"C:\ffmpeg\ffmpeg.exe"
    )

    created_paths = []

    def fake_run(cmd, capture_output, text):
        created_paths.append(cmd[-1])
        Path(cmd[-1]).write_bytes(b"RIFF....WAVEfmt ")
        return _mock_completed_process(returncode=0)

    monkeypatch.setattr("app.core.audio_file_loader.subprocess.run", fake_run)

    import numpy as np

    fake_audio = np.zeros(1600, dtype=np.float32)

    def fake_load_audio(path):
        # Only the recursive call for the temp .wav should reach here.
        assert path == created_paths[-1]
        assert Path(path).exists()
        return fake_audio

    monkeypatch.setattr(AudioFileLoader, "load_audio", staticmethod(fake_load_audio))

    result = VideoAudioExtractor.extract_and_load(str(video_path))

    assert result is fake_audio
    assert created_paths
    assert not Path(created_paths[0]).exists(), "temp wav must be removed after load"


def test_extract_and_load_deletes_temp_wav_when_load_step_fails(tmp_path, monkeypatch):
    video_path = tmp_path / "input.mp4"
    video_path.write_bytes(b"fake video bytes")

    monkeypatch.setattr(
        "app.core.audio_file_loader.shutil.which", lambda name: r"C:\ffmpeg\ffmpeg.exe"
    )

    created_paths = []

    def fake_run(cmd, capture_output, text):
        created_paths.append(cmd[-1])
        Path(cmd[-1]).write_bytes(b"RIFF....WAVEfmt ")
        return _mock_completed_process(returncode=0)

    monkeypatch.setattr("app.core.audio_file_loader.subprocess.run", fake_run)

    def fake_load_audio(path):
        raise AudioLoadError("corrupt wav")

    monkeypatch.setattr(AudioFileLoader, "load_audio", staticmethod(fake_load_audio))

    with pytest.raises(AudioLoadError, match="corrupt wav"):
        VideoAudioExtractor.extract_and_load(str(video_path))

    assert created_paths
    assert not Path(created_paths[0]).exists(), "temp wav must be removed even if load fails"


def test_load_audio_dispatches_video_files_to_extractor(tmp_path, monkeypatch):
    video_path = tmp_path / "input.mp4"
    video_path.write_bytes(b"fake video bytes")

    sentinel = object()
    called_with = {}

    def fake_extract_and_load(path):
        called_with["path"] = path
        return sentinel

    monkeypatch.setattr(VideoAudioExtractor, "extract_and_load", staticmethod(fake_extract_and_load))

    result = AudioFileLoader.load_audio(str(video_path))

    assert result is sentinel
    assert called_with["path"] == str(video_path)
