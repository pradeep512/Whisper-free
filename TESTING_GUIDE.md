# File Transcription Feature - Testing Guide

## Current Status

✅ **Feature Implementation:** Complete
✅ **WAV/FLAC/OGG Support:** Working (tested)
❌ **MP3/M4A/WebM Support:** Requires ffmpeg installation

---

## Quick Test (Works Now!)

### 1. Test with WAV file (No ffmpeg needed)

```bash
# Start the application
cd /home/kalicobra477/github/Whisper-free
source venv/bin/activate
python -m app.main
```

**In the GUI:**
1. Click **"File Transcribe"** tab
2. Click **"Browse..."**
3. Navigate to `/tmp/` and select **`test_audio.wav`** (I created this test file)
4. Click **"Transcribe File"**
5. Watch the progress bar
6. Verify transcription appears
7. Check that `/tmp/test_audio.txt` was created

**Expected result:** Works perfectly! (It's just a 440Hz tone, so transcription might be "[No speech detected]" - that's normal)

### 2. Test with Real Audio WAV

If you have any WAV files, try those. Or convert your M4A:

```bash
# Install ffmpeg first (requires sudo)
sudo apt-get install ffmpeg

# Convert M4A to WAV
ffmpeg -i "your-file.m4a" -ar 16000 -ac 1 "your-file.wav"
```

Then transcribe the WAV file.

---

## Install FFmpeg for Full Support

### Kali Linux / Debian / Ubuntu

```bash
sudo apt-get update
sudo apt-get install -y ffmpeg libsndfile1
```

### Verify Installation

```bash
ffmpeg -version
```

### Test After Installing ffmpeg

1. Restart the application
2. Try your M4A file again
3. Should work now!

---

## Format Support Matrix

| Format | Works Without FFmpeg? | Works With FFmpeg? | Notes |
|--------|----------------------|-------------------|-------|
| WAV    | ✅ Yes               | ✅ Yes            | Best compatibility |
| FLAC   | ✅ Yes               | ✅ Yes            | Lossless audio |
| OGG    | ✅ Yes               | ✅ Yes            | Open format |
| MP3    | ❌ No                | ✅ Yes            | Most common |
| M4A    | ❌ No                | ✅ Yes            | Apple format |
| OPUS   | ❌ No                | ✅ Yes            | Modern codec |
| WebM   | ❌ No                | ✅ Yes            | Web format |

---

## Complete Test Checklist

### Phase 1: Basic UI (No audio needed)
- [ ] Launch app successfully
- [ ] "File Transcribe" tab visible in sidebar
- [ ] Click tab - panel loads
- [ ] Browse button works
- [ ] File dialog opens
- [ ] Transcribe button disabled (no file selected)

### Phase 2: WAV File Test
- [ ] Select `/tmp/test_audio.wav`
- [ ] File path displays
- [ ] Duration shows (~3 seconds)
- [ ] Transcribe button enabled
- [ ] Click "Transcribe File"
- [ ] Progress bar animates (5% → 20% → 40% → 80% → 100%)
- [ ] Status messages update
- [ ] Transcription completes
- [ ] Text appears in result area
- [ ] `/tmp/test_audio.txt` created
- [ ] Copy button works
- [ ] Open button works
- [ ] Clear button resets panel

### Phase 3: M4A File Test (After installing ffmpeg)
- [ ] Install ffmpeg
- [ ] Restart app
- [ ] Select M4A file
- [ ] File loads successfully
- [ ] Duration displays
- [ ] Transcription completes
- [ ] .txt file created

### Phase 4: Database Integration
- [ ] Go to History tab
- [ ] File transcription appears in history
- [ ] Timestamp is recent
- [ ] Text matches

### Phase 5: Error Handling
- [ ] Try transcribing M4A without ffmpeg
- [ ] Clear, helpful error message displayed
- [ ] Suggests installing ffmpeg
- [ ] App doesn't crash

---

## Troubleshooting

### Error: "ffmpeg is not installed"
**Solution:** Install ffmpeg:
```bash
sudo apt-get install ffmpeg
```

### Error: "No speech detected"
**Reason:** The test file is just a tone, not speech. This is expected behavior.
**Solution:** Use a file with actual speech.

### Error: "Audio loading error"
**Check:**
1. File format is supported
2. File is not corrupted
3. File permissions are correct
4. ffmpeg is installed (for MP3/M4A)

### Progress bar stuck
**Check:**
1. Console logs for errors
2. GPU/CUDA is working
3. Whisper model is loaded

### UI freezes
**This should not happen!** The worker thread should prevent freezing.
**Report this bug with console logs.**

---

## Performance Expectations

| File Length | Expected Time | Notes |
|------------|---------------|-------|
| < 1 minute | 10-30 seconds | Very fast |
| 5 minutes  | 1-2 minutes   | Normal |
| 30 minutes | 5-10 minutes  | Longer wait |
| > 1 hour   | 15+ minutes   | Be patient |

*Times vary based on GPU, model size, and file complexity.*

---

## Test Results Logging

After testing, please note:

**What worked:**
- ✅
- ✅
- ✅

**What didn't work:**
- ❌
- ❌

**Observations:**
-

**System Info:**
- OS: Kali Linux
- Python: 3.13.7
- ffmpeg installed: [ ] Yes [ ] No
- GPU available: [ ] Yes [ ] No

---

## Next Steps After Testing

1. **If WAV works:** Install ffmpeg for full format support
2. **If everything works:** Feature is ready for production use!
3. **If issues found:** Check console logs and report

---

## Quick Command Reference

```bash
# Launch app
cd /home/kalicobra477/github/Whisper-free
source venv/bin/activate
python -m app.main

# Install ffmpeg
sudo apt-get install ffmpeg

# Convert audio to WAV
ffmpeg -i input.m4a -ar 16000 -ac 1 output.wav

# Check logs
python -m app.main 2>&1 | tee debug.log
```

---

**Testing Time:** 15-30 minutes
**Difficulty:** Easy
**Status:** Ready to test!
