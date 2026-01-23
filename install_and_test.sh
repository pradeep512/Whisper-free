#!/bin/bash
# Quick Install and Test Script for File Transcription Feature

set -e

echo "=================================================="
echo "File Transcription Feature - Install & Test"
echo "=================================================="
echo

# Check if we're in the right directory
if [ ! -f "app/main.py" ]; then
    echo "❌ Error: Please run this from the Whisper-free directory"
    exit 1
fi

# Check if venv exists
if [ ! -d "venv" ]; then
    echo "❌ Error: Virtual environment not found"
    echo "Run: python -m venv venv"
    exit 1
fi

# Activate venv
echo "✓ Activating virtual environment..."
source venv/bin/activate

# Check Python packages
echo "✓ Checking Python packages..."
pip list | grep -q librosa || pip install librosa
pip list | grep -q soundfile || pip install soundfile
pip list | grep -q audioread || pip install audioread

# Check ffmpeg
echo
echo "Checking ffmpeg installation..."
if command -v ffmpeg &> /dev/null; then
    echo "✅ ffmpeg is installed"
    ffmpeg -version | head -1
else
    echo "❌ ffmpeg is NOT installed"
    echo
    echo "Install with:"
    echo "  sudo apt-get install ffmpeg"
    echo
    echo "You can still test WAV files without ffmpeg."
    echo "MP3/M4A files will require ffmpeg."
fi

# Create test WAV file
echo
echo "Creating test audio file..."
python -c "
import numpy as np
import soundfile as sf
duration = 3
sample_rate = 16000
t = np.linspace(0, duration, int(sample_rate * duration))
audio = 0.3 * np.sin(2 * np.pi * 440 * t).astype(np.float32)
sf.write('/tmp/test_audio.wav', audio, sample_rate)
print('✓ Created: /tmp/test_audio.wav')
"

# Test audio loading
echo
echo "Testing AudioFileLoader..."
python -c "
from app.core.audio_file_loader import AudioFileLoader
import sys

test_file = '/tmp/test_audio.wav'
try:
    is_valid, error = AudioFileLoader.validate_file(test_file)
    if not is_valid:
        print(f'❌ Validation failed: {error}')
        sys.exit(1)

    duration = AudioFileLoader.get_duration(test_file)
    audio = AudioFileLoader.load_audio(test_file)

    print(f'✅ WAV loading works!')
    print(f'   Duration: {duration:.2f}s')
    print(f'   Samples: {audio.shape[0]}')
    print(f'   Format: {audio.dtype}')
except Exception as e:
    print(f'❌ Test failed: {e}')
    sys.exit(1)
"

# Summary
echo
echo "=================================================="
echo "Setup Complete!"
echo "=================================================="
echo
echo "Next steps:"
echo "1. Launch the app:"
echo "   python -m app.main"
echo
echo "2. In the app:"
echo "   - Click 'File Transcribe' tab"
echo "   - Browse to: /tmp/test_audio.wav"
echo "   - Click 'Transcribe File'"
echo
echo "3. For MP3/M4A support:"
echo "   sudo apt-get install ffmpeg"
echo
echo "Documentation:"
echo "  - README_FILE_TRANSCRIPTION.md"
echo "  - TESTING_GUIDE.md"
echo
echo "Happy transcribing! 🎉"
