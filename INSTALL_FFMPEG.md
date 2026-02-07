# FFmpeg Installation Required

The File Transcription feature needs **ffmpeg** to handle certain audio formats.

## Quick Install (Kali Linux)

```bash
sudo apt-get update
sudo apt-get install -y ffmpeg libsndfile1
```

## Verify Installation

```bash
ffmpeg -version
```

## What Works Without FFmpeg?

- ✅ **WAV files** - Work without ffmpeg (using soundfile)
- ❌ **MP3 files** - Require ffmpeg
- ❌ **M4A files** - Require ffmpeg
- ❌ **WebM files** - Require ffmpeg
- ✅ **FLAC files** - Work without ffmpeg (using soundfile)
- ✅ **OGG files** - Work without ffmpeg (using soundfile)

## Test After Installing

1. Install ffmpeg (command above)
2. Restart the application
3. Try transcribing the M4A file again

## Alternative: Convert M4A to WAV

If you can't install ffmpeg right now, convert your file:

```bash
# Using online converter or if ffmpeg is available elsewhere
ffmpeg -i "input.m4a" -ar 16000 -ac 1 "output.wav"
```

Then transcribe the WAV file.
