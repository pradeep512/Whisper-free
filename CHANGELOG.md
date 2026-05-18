# Changelog

All notable changes to Whisper-Free.

The format is loosely based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [1.0.0] — 2026-05-18 — macOS support 🎉

First-class macOS support alongside the existing Linux build. Same UX, native macOS feel.

### Added — macOS

- **Apple Silicon support** via the [MLX framework](https://github.com/ml-explore/mlx) and [`mlx-whisper`](https://github.com/ml-explore/mlx-examples/tree/main/whisper). All six Whisper model sizes — tiny / base / small / medium / large / large-v3-turbo — load and transcribe via Metal. M1 / M2 / M3 / M4 Macs all supported; Intel Macs are not.
- **Menu bar agent UX**. App lives as an `NSStatusItem` (no Dock icon by default); left-click toggles recording, right-click opens a context menu (Toggle / Open Window / Quit). The main settings window is reachable via "Open Window…".
- **Dynamic Island overlay** that appears across all Spaces, floats above full-screen apps, and stays visible when the app loses focus (Slack / Safari / Xcode / whatever's in front).
- **Onboarding wizard** for Microphone + Accessibility permission grants on first launch.
- **Open at Login** toggle (via `SMAppService`, macOS 13+).
- **Show in Dock** toggle (live; flips `NSApp.setActivationPolicy()` without a restart).
- **`whisper-free` CLI shim** installed alongside the app — `whisper-free --toggle` sends a recording-toggle command to the running instance via Unix-domain-socket IPC. Useful with Raycast / Alfred / Keyboard Maestro.
- **Direct DMG distribution** via GitHub Releases. Optional Homebrew Cask: `brew install --cask whisper-free` (once the cask PR is merged).

### Added — cross-platform

- Central theme module (`app/ui/theme.py`) with macOS-style coral-orange accent, custom `ModernCheckBox` widget, gradient primary buttons, capsule sidebar selection, system-font stack.
- Transcribe panel laid out as a 2×2 grid of control cards (Select / Settings / Output Formats / Transcribe) with the Result panel below.
- Settings panel laid out as a 3×2 grid (Whisper Model / Audio / Hotkey / Overlay / macOS / Advanced).
- Platform-aware engine factory (`create_whisper_engine`) that dispatches to MLX on Apple Silicon and PyTorch elsewhere.
- Platform-aware `valid_models()` + `model_memory_reqs()` helpers so the UI only ever offers models the active engine can actually load.

### Changed

- `requirements.txt` split into `requirements-base.txt` + `requirements-linux.txt` + `requirements-macos.txt`. The macOS bundle drops `torch` / `torchaudio` / `openai-whisper` entirely (saves ~2 GB).
- Storage layout reorganized per Apple's File System Programming Guide:
  - `~/Library/Application Support/Whisper-Free/` — config, history DB
  - `~/Library/Caches/Whisper-Free/` — downloaded Whisper models
  - `~/Library/Logs/Whisper-Free/` — log files
  - Linux still uses `~/.config/whisper-free/` (no behavior change).
- "File Transcribe" tab renamed to "Transcribe".
- Sidebar nav items get tighter padding and a capsule selection pill instead of a flat rectangle.

### Fixed

- Multiprocessing fork bomb when the bundled `.app` triggered Python's `spawn` start method (transitive via `huggingface_hub` parallel downloads). Now calls `multiprocessing.freeze_support()` at the top of `main()`.
- Microphone capture returning a zero-filled stream on macOS because `sounddevice`/PortAudio doesn't always trigger TCC. Now primes TCC via `AVCaptureDevice.requestAccess` at startup.
- Overlay disappearing when switching to another app. Now sets `NSPanel.setHidesOnDeactivate_(False)` and `NSStatusWindowLevel`.
- Overlay not appearing when recording was triggered by a click (vs the hotkey). Now uses `QTimer.singleShot(0, …)` deferred `show()+raise_()` to defeat the focus race.
- Settings panel "Save" crashing because `HotkeyManager.change_hotkey()` re-instantiated a `pynput.GlobalHotKeys` listener while the Qt event loop was running, which aborts with SIGTRAP from Quartz. macOS now skips the live reload and shows a "restart required" dialog instead.
- Settings panel overflowing horizontally at the 880-px default window width. Compacted card padding and reduced `QComboBox` min-width.
- First-launch download dialog flashing briefly on every relaunch even when the model was cached, AND interfering with `pynput` due to its `ApplicationModal` flag. Now uses a cache-detection helper to skip the dialog when the model is already downloaded; when shown it's non-modal.
- `WhisperEngine.transcribe()` raising `Invalid model_name: 'large'` on macOS because the Settings dropdown was populated from the Linux engine's hard-coded list. Settings now uses platform-aware `valid_models()`.

### Known limitations in v1.0.0

See [`KNOWN_ISSUES.md`](KNOWN_ISSUES.md) for the full list. Summary:

- The app is **unsigned** — first launch triggers a Gatekeeper warning (`right-click → Open` or System Settings → Privacy & Security → "Open Anyway").
- **Corporate MDM** (Workspace ONE / Airwatch / Jamf) deploying PPPC profiles will silently block Accessibility for unsigned apps. The menu bar / file transcribe / batch flows all still work; only the global hotkey requires Accessibility.
- The global hotkey supports modifier+key combos only (default `cmd+shift+space`); single-key tap-toggle requires custom listener work planned for v1.1.

---

## Previous

See git history before v1.0.0 for the Linux-only changelog.
