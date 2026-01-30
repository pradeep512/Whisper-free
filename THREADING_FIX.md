# Threading Fix: PTT Completion Callback

**Date**: 2026-01-30
**Issue**: PTT only works once, UI freezes, history doesn't update
**Severity**: Critical
**Status**: ✅ FIXED

---

## Problem Description

After the first PTT transcription:
- ✅ Transcription works and copies to clipboard
- ❌ History doesn't update (though DB entry is created)
- ❌ UI becomes unresponsive
- ❌ Cannot perform another PTT (hotkey ignored)
- ❌ State machine stuck in COMPLETED

## Root Cause

**Qt Threading Violation**

The PTT completion callback (`_on_ptt_transcription_complete`) was being invoked directly from the TranscriptionQueueManager's worker thread. This callback then tried to:

1. Update the state machine
2. Create QTimer instances
3. Update UI components
4. Trigger history panel refresh (which uses QTimer)

All Qt objects (QTimer, state machine, UI widgets) **must** be accessed only from the main Qt thread. Accessing them from worker threads causes:

```
QObject::startTimer: Timers cannot be started from another thread
QObject::killTimer: Timers cannot be stopped from another thread
QObject::startTimer: Timers can only be used with threads started with QThread
```

These errors caused:
- Timers to fail silently
- State machine to not reset to IDLE
- History panel to not refresh
- UI to freeze

## Solution

**Use Qt Signals for Thread-Safe Communication**

Qt signals are inherently thread-safe and automatically marshal calls to the correct thread. The fix:

### Changes Made

**File**: `app/main.py`

1. **Added new signal**:
   ```python
   ptt_transcription_complete_signal = Signal(str, str, float)  # text, language, duration
   ```

2. **Connected signal in `_connect_signals()`**:
   ```python
   self.ptt_transcription_complete_signal.connect(self.on_transcription_complete)
   ```

3. **Modified `_on_ptt_transcription_complete()` to emit signal**:
   ```python
   def _on_ptt_transcription_complete(self, text: str, result_data: dict):
       # Extract metadata (still in worker thread - OK, just data processing)
       language = result_data.get('language', 'en')
       segments = result_data.get('segments', [])
       duration = segments[-1].get('end', 0.0) if segments else 0.0

       # Emit signal to main thread (Qt automatically handles thread crossing)
       self.ptt_transcription_complete_signal.emit(text, language, duration)
   ```

### How It Works

**Before (Broken)**:
```
Worker Thread                   Main Thread
     │                               │
     ├─ Job completes               │
     ├─ Callback: _on_ptt_...       │
     ├─ Call on_transcription_...  │
     │   ├─ QTimer.singleShot()    │ ❌ WRONG THREAD
     │   ├─ state.transition_to()  │ ❌ WRONG THREAD
     │   └─ history.load_history() │ ❌ WRONG THREAD
     │       └─ QTimer.start()     │ ❌ WRONG THREAD
```

**After (Fixed)**:
```
Worker Thread                   Main Thread
     │                               │
     ├─ Job completes               │
     ├─ Callback: _on_ptt_...       │
     ├─ Emit signal ───────────────▶│
     │                               ├─ Signal received
     │                               ├─ on_transcription_...
     │                               │   ├─ QTimer.singleShot() ✅
     │                               │   ├─ state.transition_to() ✅
     │                               │   └─ history.load_history() ✅
     │                               │       └─ QTimer.start() ✅
```

## Testing

### Before Fix
- PTT works once
- Second PTT attempt ignored (state=COMPLETED)
- History shows entry in DB but not in UI
- Console shows Qt timer errors

### After Fix
- PTT works repeatedly ✅
- History updates after each transcription ✅
- State resets to IDLE after 2.5s ✅
- No Qt threading errors ✅

### Test Procedure

1. Run application: `python -m app.main`
2. Press Ctrl+Space, record audio, press Ctrl+Space again
3. Verify:
   - Transcription copied to clipboard ✅
   - History panel updates with new entry ✅
   - After 2.5s, state returns to IDLE ✅
   - Can perform another PTT immediately ✅
4. Repeat 3-5 times to confirm no degradation

## Technical Details

### Qt Signal/Slot Mechanism

Qt signals are thread-safe because:
- When signal is emitted from thread A to slot in thread B
- Qt automatically queues the call in thread B's event loop
- The slot executes in thread B's context
- This is called "Queued Connection" (automatic across threads)

### Why This Pattern

This is the correct Qt pattern for worker thread → main thread communication:

✅ **DO**: Emit signals from worker threads
✅ **DO**: Connect signals to main thread slots
❌ **DON'T**: Directly call main thread methods from workers
❌ **DON'T**: Create Qt objects (timers, widgets) in worker threads
❌ **DON'T**: Access Qt objects from multiple threads

## Related Issues

This same pattern applies to:
- File transcription completion
- Batch transcription updates
- Model loading completion
- Any worker thread → UI communication

All these already use signals correctly and don't have this issue.

## Prevention

To prevent similar issues in future:

1. **Always use signals** for cross-thread communication
2. **Never call** main thread methods directly from workers
3. **Check logs** for "Timers cannot be started" warnings
4. **Test thoroughly** - threading bugs often appear on second use

## References

- [Qt Threading Basics](https://doc.qt.io/qt-6/threads-qobject.html)
- [Qt Thread-Safety](https://doc.qt.io/qt-6/threads-reentrancy.html)
- [PySide6 Signals and Slots](https://doc.qt.io/qtforpython/overviews/signalsandslots.html)

---

**Fix Committed**: 2026-01-30
**Tested By**: User kalicobra477
**Status**: Ready for production
