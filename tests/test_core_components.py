#!/usr/bin/env python3
"""
Quick test for WhisperEngine and AudioRecorder

This script tests the core audio capture and transcription components
of Whisper-Free to ensure they work correctly before integration.

Usage:
    python3 tests/test_core_components.py

Requirements:
    - Working microphone
    - CUDA-capable GPU (for GPU tests)
    - Whisper models will be downloaded on first run (~150MB for tiny)
"""

import sys
import time
import numpy as np
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from app.core.whisper_engine import WhisperEngine
from app.core.audio_capture import AudioRecorder


def print_header(text: str) -> None:
    """Print a formatted section header."""
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}\n")


def test_audio_devices():
    """Test device enumeration."""
    print_header("Testing Audio Devices")

    devices = AudioRecorder.list_devices()

    if not devices:
        print("  WARNING: No input devices found!")
        return False

    print(f"  Found {len(devices)} input device(s):\n")
    for dev in devices:
        print(
            f"  [{dev['index']:2d}] {dev['name']:<40} "
            f"({dev['channels']} ch @ {dev['sample_rate']} Hz)"
        )

    print()
    return True


def test_whisper_loading():
    """Test Whisper model loading."""
    print_header("Testing Whisper Model Loading")

    try:
        # Test CUDA availability first
        import torch
        if torch.cuda.is_available():
            device = "cuda"
            gpu_name = torch.cuda.get_device_name(0)
            print(f"  CUDA available: {gpu_name}\n")
        else:
            device = "cpu"
            print("  CUDA not available, using CPU (slow)\n")

        # Load tiny model (fastest, smallest)
        print("  Loading 'tiny' model (this may take a moment on first run)...")
        engine = WhisperEngine(model_name="tiny", device=device)

        # Check VRAM usage
        vram = engine.get_vram_usage()
        if device == "cuda":
            print(f"  Model loaded successfully!")
            print(f"  VRAM usage: {vram:.1f} MB")
        else:
            print(f"  Model loaded successfully on CPU")

        # Test model representation
        print(f"  Engine state: {engine}")

        # Cleanup
        engine.cleanup()
        print(f"  Cleanup complete\n")

        return True

    except Exception as e:
        print(f"  ERROR: {e}\n")
        return False


def test_recording(duration: int = 5):
    """Test audio recording."""
    print_header(f"Testing Audio Recording ({duration} seconds)")

    try:
        recorder = AudioRecorder()
        print(f"  Recorder initialized: {recorder}\n")

        print(f"  Recording for {duration} seconds...")
        print(f"  Please speak into your microphone!\n")

        recorder.start()

        # Monitor levels during recording
        for i in range(duration):
            time.sleep(1)

            levels = recorder.get_waveform_data()
            if levels:
                avg_level = np.mean(levels)
                max_level = np.max(levels)
                bar_length = int(max_level * 40)
                bar = '█' * bar_length + '░' * (40 - bar_length)
            else:
                avg_level = 0.0
                max_level = 0.0
                bar = '░' * 40

            print(
                f"  [{i+1}/{duration}s] "
                f"Level: {max_level:4.2f} [{bar}]"
            )

        # Stop and get audio
        audio = recorder.stop()

        print(f"\n  Recording stopped!")
        print(f"  Captured {len(audio)} samples ({len(audio)/16000:.2f}s)")
        print(f"  Audio shape: {audio.shape}, dtype: {audio.dtype}")
        print(f"  Audio range: [{audio.min():.3f}, {audio.max():.3f}]")

        # Check if we got valid audio
        if len(audio) == 0:
            print("  WARNING: No audio captured!")
            return None

        if np.all(audio == 0):
            print("  WARNING: Audio is all zeros (no input detected)!")
            return None

        print()
        return audio

    except Exception as e:
        print(f"  ERROR: {e}\n")
        import traceback
        traceback.print_exc()
        return None


def test_transcription(audio: np.ndarray):
    """Test transcription."""
    print_header("Testing Transcription")

    if audio is None or len(audio) == 0:
        print("  Skipping transcription (no audio data)\n")
        return False

    try:
        # Use tiny model for speed
        import torch
        device = "cuda" if torch.cuda.is_available() else "cpu"

        print(f"  Loading Whisper model (device: {device})...")
        engine = WhisperEngine(model_name="tiny", device=device)

        print(f"  Transcribing {len(audio)/16000:.2f}s of audio...")
        start_time = time.time()

        result = engine.transcribe(audio, language='en')

        elapsed = time.time() - start_time

        # Display results
        print(f"\n  Transcription complete in {elapsed:.2f}s!")
        print(f"  {'─'*56}")
        print(f"  Text:     {result['text']}")
        print(f"  {'─'*56}")
        print(f"  Language: {result['language']}")
        print(f"  Duration: {result['duration']:.2f}s")
        print(f"  Segments: {len(result['segments'])}")

        if result['segments']:
            print(f"\n  Segment details:")
            for i, seg in enumerate(result['segments'][:3]):  # Show first 3
                print(
                    f"    [{seg['start']:5.1f}s - {seg['end']:5.1f}s]: "
                    f"{seg['text'].strip()}"
                )
            if len(result['segments']) > 3:
                print(f"    ... and {len(result['segments']) - 3} more segments")

        # Test model change
        print(f"\n  Testing model hot-swap...")
        engine.change_model('base')
        print(f"  Model changed to 'base'")

        # Cleanup
        engine.cleanup()
        print(f"  Cleanup complete\n")

        return True

    except Exception as e:
        print(f"  ERROR: {e}\n")
        import traceback
        traceback.print_exc()
        return False


def test_edge_cases():
    """Test edge cases and error handling."""
    print_header("Testing Edge Cases")

    try:
        import torch
        device = "cuda" if torch.cuda.is_available() else "cpu"

        engine = WhisperEngine(model_name="tiny", device=device)

        # Test 1: Empty audio
        print("  Test 1: Empty audio array...")
        try:
            empty_audio = np.array([], dtype=np.float32)
            engine.transcribe(empty_audio)
            print("    FAIL: Should have raised ValueError")
        except ValueError as e:
            print(f"    PASS: Caught ValueError as expected")

        # Test 2: Invalid shape
        print("  Test 2: Invalid audio shape (2D)...")
        try:
            stereo_audio = np.random.randn(100, 2).astype(np.float32)
            engine.transcribe(stereo_audio)
            print("    FAIL: Should have raised ValueError")
        except ValueError as e:
            print(f"    PASS: Caught ValueError as expected")

        # Test 3: Silent audio
        print("  Test 3: Silent audio (all zeros)...")
        try:
            silent_audio = np.zeros(16000, dtype=np.float32)  # 1 second of silence
            result = engine.transcribe(silent_audio)
            print(f"    PASS: Transcribed (result: '{result['text']}')")
        except Exception as e:
            print(f"    WARN: Failed with {e}")

        # Test 4: Very short audio
        print("  Test 4: Very short audio (0.1s)...")
        try:
            short_audio = np.random.randn(1600).astype(np.float32) * 0.1
            result = engine.transcribe(short_audio)
            print(f"    PASS: Transcribed (result: '{result['text']}')")
        except Exception as e:
            print(f"    WARN: Failed with {e}")

        # Test 5: Invalid model name
        print("  Test 5: Invalid model name...")
        try:
            bad_engine = WhisperEngine(model_name="invalid_model")
            print("    FAIL: Should have raised ValueError")
        except ValueError as e:
            print(f"    PASS: Caught ValueError as expected")

        engine.cleanup()
        print()

        return True

    except Exception as e:
        print(f"  ERROR: {e}\n")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("\n" + "="*60)
    print("  Whisper-Free Core Components Test Suite")
    print("="*60)

    results = {}

    # Test 1: Audio devices
    results['devices'] = test_audio_devices()

    # Test 2: Whisper loading
    results['whisper_load'] = test_whisper_loading()

    # Test 3: Audio recording
    audio = test_recording(duration=5)
    results['recording'] = audio is not None

    # Test 4: Transcription
    if audio is not None:
        results['transcription'] = test_transcription(audio)
    else:
        print_header("Skipping Transcription Test")
        print("  No audio data available (recording failed)\n")
        results['transcription'] = False

    # Test 5: Edge cases
    results['edge_cases'] = test_edge_cases()

    # Summary
    print_header("Test Summary")
    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for test_name, passed_test in results.items():
        status = "✅ PASS" if passed_test else "❌ FAIL"
        print(f"  {status}  {test_name.replace('_', ' ').title()}")

    print(f"\n  {'─'*56}")
    print(f"  Results: {passed}/{total} tests passed")
    print(f"  {'─'*56}\n")

    if passed == total:
        print("  🎉 All tests completed successfully!")
        return 0
    else:
        print("  ⚠️  Some tests failed. Please check the output above.")
        return 1


if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n\n  Interrupted by user. Exiting...")
        sys.exit(130)
    except Exception as e:
        print(f"\n\n  FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
