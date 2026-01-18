# Kali Linux Push‑to‑Talk Dictation App (Clipboard‑Only) — Design Notes

This document summarizes: what you should use, what to check on Kali Linux (X11 vs Wayland), and a practical build plan for a push‑to‑talk speech‑to‑text app that **streams audio over OpenAI Realtime WebSocket** and **copies transcripts to the clipboard** (no keystroke injection).

---

## 1) Your target behavior (agreed scope)

### Hotkey
- **Global hotkey:** `Ctrl + Space`
- **Press & hold:** start recording (push‑to‑talk)
- **Release:** stop recording, finalize transcript

### Output
- Transcript is placed into the **clipboard** automatically.
- User pastes manually with `Ctrl + V`.

### UI
- **Main window (when opened):**
  - Sidebar + settings (API key, hotkey, language, model)
  - A list of the **last 5 transcripts**
  - Live view of partial transcript while speaking (streaming deltas)
  - Clear status/errors

- **Overlay (only during push‑to‑talk):**
  - Appears at the **top of screen** when hotkey is pressed
  - Shows mic level waveform + “Listening…”
  - Shows partial transcript while speaking
  - On release: expands briefly to show final transcript and “Copied”
  - Auto‑dismiss after ~2–3 seconds (or longer on error)

---

## 2) The two platform modes (critical on Linux)

Linux is split into two display server worlds:

### A) X11 (easier)
- Global hotkeys are typically feasible.
- Always‑on‑top overlays are straightforward.

### B) Wayland (more restricted)
- Global hotkey hooks and certain overlay behaviors can be restricted depending on the desktop environment.
- You may need **desktop environment shortcuts** or **portals** to register global shortcuts.

**Recommendation:** build the app with:
- **X11 Full Mode:** global hotkey works inside your app/daemon.
- **Wayland Restricted Mode:** fallback to user‑configured desktop shortcut (or portal support when available), plus the overlay still works depending on compositor rules.

---

## 3) How to check whether Kali is using X11 or Wayland

Run these in a terminal:

### Quick check 1 (most reliable)
```bash
echo $XDG_SESSION_TYPE
```
- `x11` → you are on X11
- `wayland` → you are on Wayland

### Quick check 2 (shows session)
```bash
loginctl show-session "$XDG_SESSION_ID" -p Type
```

### XFCE note (common on Kali)
- Kali’s XFCE sessions are typically **X11** by default.
- GNOME/KDE can be Wayland depending on configuration.

---

- I checked and I'm in X11

## 4) Audio capture stack: what to use (simple + works on Kali)

You said you do not know the Linux audio stacks, so here is the practical recommendation:

### Recommended: PortAudio‑based capture (simple, cross‑distro)
Use a library that talks to the OS audio system (PipeWire/PulseAudio/ALSA) via PortAudio.

**If you choose Python**
- **`sounddevice`** (PortAudio) for microphone capture
- Very fast to prototype, good device selection, good stability.

**If you choose Rust**
- **`cpal`** for audio capture
- Performant and clean, good for a “real product”.

Why this is a good choice:
- You do not need to directly manage PipeWire vs PulseAudio vs ALSA.
- The library sits above those differences.

### Practical audio format for OpenAI Realtime
- Capture as float32 or int16, then convert to:
  - **PCM16**, mono, 16 kHz (commonly used), and base64 encode frames.

---

## 5) WebSocket approach: Realtime transcription (ongoing audio stream)

You want “ongoing audio streaming over WebSocket”. That matches the Realtime transcription flow:

- Connect to the Realtime WebSocket transcription endpoint.
- Send a session update (model, audio format).
- Append audio frames continuously while hotkey is held.
- Receive partial transcript events (`delta`) and final transcript events (`done`/segment events depending on model/options).
- Copy final transcript to clipboard.

### Keep‑alive / “warm session” idea (your 2‑minute window)
Your idea is reasonable:
- Keep the WebSocket open for **~2 minutes** after the last interaction.
- If a new push‑to‑talk starts within that window, reuse the session.
- If idle longer, close it to reduce resource usage and failure surface.

### Buffering for instant feel
To reduce “startup delay” on first use:
- Start capturing immediately on hotkey press.
- Store the first ~300–800 ms in a ring buffer.
- Open the WebSocket in parallel.
- Once connected, flush the buffered audio first, then live frames.

This typically makes the user experience feel instant.

---

## 6) API key handling (BYOK: Bring Your Own Key)

You decided:
- First run: prompt user to paste OpenAI API key.
- Store it locally.
- Settings page: allow updating/changing it.

### Important security realities
- Any desktop app storing a key can be extracted by malware on that machine.
- Still, this is acceptable for a personal tool, but:
  - Store it in **system keyring** where possible.

**Recommended on Linux**
- Use `libsecret` (GNOME Keyring / Secret Service API) if available.
- Otherwise store in `~/.config/<appname>/config.json` with clear warnings.

---

## 7) Global hotkey strategy (Ctrl+Space)

### Best‑effort design
Implement hotkey capture with:
- **X11 path:** global key hook works reliably.
- **Wayland path:** provide a fallback:
  1) user binds a desktop shortcut to “start listening”
  2) your app receives a D‑Bus message / CLI trigger / local socket signal to start/stop

Practical wayland‑safe fallback trigger options:
- Run background daemon exposing a local socket (Unix domain socket).
- Desktop shortcut calls:
  - `yourapp --toggle` or `yourapp --start` / `--stop`

This works even when true global hooks are blocked.

---

## 8) Overlay feasibility (what to check)

Overlays are usually possible on X11, but Wayland rules differ.

### On X11
- Always‑on‑top transparent window is straightforward.

### On Wayland
- An “overlay” may need to be:
  - a normal always‑on‑top window (supported by many compositors)
  - or a “layer‑shell” surface (supported in wlroots compositors; used by panels/launchers)

**Practical approach**
- Use a standard always‑on‑top window first.
- If you later need perfect panel‑like behavior, add layer‑shell support (more advanced).

---

## 9) Proposed architecture (simple and implementable)

### Processes (recommended)
**One process, two modes**
- Main app UI (Qt/GTK/Tauri)
- Background mode when minimized (tray icon optional)

OR

**Two processes (clean separation)**
- **Daemon:** hotkey + audio + WebSocket + clipboard
- **UI:** main window + overlay window, communicates with daemon (IPC)

For your scope, a **single process** can work, but two processes can be more robust.

### Core modules
1) **Hotkey Manager**
   - Detect press/release of Ctrl+Space
   - Emits events: `PTT_START`, `PTT_STOP`
   - Wayland fallback: receives CLI/IPC events

2) **Audio Capture**
   - Starts on `PTT_START`
   - Produces PCM16 frames (20 ms)
   - Stops on `PTT_STOP`

3) **Realtime WebSocket Client**
   - Manages connection lifecycle
   - Session update
   - Sends `input_audio_buffer.append`
   - Receives transcript deltas/final events
   - Keeps connection warm (2‑minute timer)

4) **Transcript Aggregator**
   - Updates live partial text for overlay & main window
   - On final transcript:
     - copies to clipboard
     - stores history (last 5 items)

5) **UI Layer**
   - Main window (history, settings, live status)
   - Overlay window (only during PTT + short after)

6) **Config + Secure Storage**
   - API key
   - model, language, hotkey config
   - remember audio device selection

---

## 10) Implementation options (recommended stack)

### Option A: Python + Qt (fastest to ship)
- UI: PySide6 (Qt)
- Audio: `sounddevice`
- WebSocket: `websockets` / `aiohttp`
- Clipboard: Qt clipboard API
- Packaging: PyInstaller → AppImage or `.deb`

### Option B: Rust + Tauri (strong product path)
- UI: Tauri
- Audio: `cpal`
- WebSocket: `tokio-tungstenite`
- Clipboard: cross‑platform clipboard crate / Tauri APIs
- Packaging: built‑in bundling for `.deb` / AppImage

For Kali/X11, **Option A** is usually the quickest path.

---

## 11) Packaging + run on startup

### Distribute
- **AppImage**: easiest for users (single file).
- **.deb**: best integration for Kali/Debian users.

### Start on boot (user session)
- **Autostart file:**
  - `~/.config/autostart/yourapp.desktop`
- Or **systemd user service:**
  - `~/.config/systemd/user/yourapp.service`

---

## 12) Suggested “phase plan” (lowest risk)

### Phase 1 (MVP, X11 first)
- Hotkey works on X11.
- Overlay shows listening + partial transcript.
- Final transcript copied to clipboard + stored in history.
- Main window shows last 5 transcripts.

### Phase 2 (Wayland compatibility + fallback triggers)
- Add “desktop shortcut triggers daemon” method.
- Improve overlay behavior on Wayland if needed.

### Phase 3 (polish)
- Device selection UI
- Better error states + reconnect
- Optional tray icon
- Optional local VAD / noise reduction

---

## 13) Open questions you should test early (before heavy coding)

1) Does your Kali session run X11 or Wayland? (run the checks above)
2) Can your chosen toolkit create a top overlay that appears at screen top on your desktop environment?
3) Can you reliably capture Ctrl+Space globally on your setup?
4) Mic device permissions: is capture allowed without extra prompts?

Testing these early avoids wasting time.

---

## 14) What you asked for: “what we are going to do” summary

- Build a Linux desktop app that:
  - listens on Ctrl+Space
  - streams mic audio via Realtime WebSocket transcription
  - displays a temporary overlay during listening/transcribing
  - copies final transcript into clipboard
  - shows last 5 transcripts in the main app
  - stores API key from user input (settings editable)
  - optionally starts on login

- Implement with an X11‑first approach and a Wayland fallback trigger strategy.

---

If you tell me your **Kali desktop environment** (XFCE / GNOME / KDE) and what `echo $XDG_SESSION_TYPE` prints, I can recommend the best hotkey + overlay implementation path for your exact setup.
