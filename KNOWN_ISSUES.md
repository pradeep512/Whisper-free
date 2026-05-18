# Known Issues — Whisper-Free macOS

Status as of **v1.0.0**. Most items flagged during the port were resolved
during dogfooding. The remaining list is short and well-understood.

---

## Confirmed working in v1.0.0

- **Push-to-talk** via global hotkey, menu bar click, in-app Record button — all three paths route to MLX and produce real English text, copied to clipboard, saved to history.
- **Dynamic Island overlay** appears on every Space, visible above full-screen apps, stays visible when our app loses focus.
- **File transcription** for WAV / MP3 / M4A / FLAC / OGG / OPUS / WebM (with ffmpeg from Homebrew).
- **Batch transcription** with per-file progress and high-priority PTT pre-emption.
- **Settings persistence** in `~/Library/Application Support/Whisper-Free/`; model swap downloads on demand and caches to `~/Library/Caches/Whisper-Free/`.
- **Open at Login** + **Show in Dock** toggles via SMAppService.
- All six MLX Whisper model sizes (tiny / base / small / medium / large / large-v3-turbo).

---

## Open issues

### 🟧 Corporate MDM blocks Accessibility (out of our control)

**Affects**: Macs enrolled in Workspace ONE / Airwatch / Jamf / similar MDMs that deploy a PPPC (Privacy Preferences Policy Control) profile.

**Symptom**: Even after the user adds Whisper-Free to System Settings → Privacy & Security → Accessibility and toggles it on, the global hotkey doesn't fire. The log shows `pynput.keyboard.GlobalHotKeys - WARNING - This process is not trusted!`

**Cause**: MDM-deployed PPPC profiles match apps by **bundle identifier + code signature**. Whisper-Free v1.0.0 is unsigned, so it doesn't match any allow-list entry. The MDM silently denies the trust grant regardless of the user-visible toggle. `tccutil reset Accessibility` doesn't help — the deny isn't in TCC's cache, it's in the policy layer above it.

**Workarounds** (the app is fully functional minus the hotkey):
- **Menu bar mic icon** — left-click to start/stop. No Accessibility required.
- **File / Batch transcribe panels** — no Accessibility required.
- **`whisper-free --toggle`** CLI shim — wire to a managed app like Raycast or Keyboard Maestro that's already on the corporate allow-list.

**Permanent fix**: requires
1. Enrolling in the Apple Developer Program ($99/yr) and code-signing the build with Developer ID, and
2. Asking the corporate IT admin to add `com.whisperfree.app` to the PPPC profile.

This is not a Whisper-Free bug — it's a macOS enterprise-policy interaction. Personal / unmanaged Macs are unaffected.

### 🟨 Global hotkey is modifier-key combos only

We default to `cmd+shift+space` because `pynput.keyboard.GlobalHotKeys` is designed for modifier-key combinations. **Single-key hotkeys like Right Option** (which we'd prefer to mirror native macOS Dictation) don't work with `GlobalHotKeys` — they need `pynput.keyboard.Listener` with custom tap-toggle detection.

**Workaround**: stick with `cmd+shift+space` (or change to any other modifier+key in Settings).

**Fix planned for v1.1**: add a single-key listener path in `HotkeyManager`.

### 🟨 Unsigned binary triggers Gatekeeper warning on first launch

**Symptom**: macOS 13–14 shows *"Whisper-Free can't be opened because Apple cannot check it for malicious software"* on first launch. macOS 15+ requires going to System Settings → Privacy & Security → "Open Anyway".

**Workaround**: documented in the README install section.

**Permanent fix**: Apple Developer Program enrollment + Developer ID code signing + notarization via `xcrun notarytool`. Planned for v1.x once funded.

### 🟨 Accessibility grant must be repeated after each binary update

Because the build is unsigned, every new release has a different binary identity from macOS's perspective. When you replace `/Applications/Whisper-Free.app` (e.g. `brew upgrade`), the previous Accessibility grant becomes stale. macOS often shows the toggle as still on but actually denies trust until you remove + re-add the entry.

**Workaround**: after upgrading, open System Settings → Privacy & Security → Accessibility, click `-` next to Whisper-Free, then re-add the updated app.

**Permanent fix**: code signing (same as above). Signed apps keep their identity across updates.

### 🟨 First-time PTT after large model swap shows no progress

Switching models in Settings → Whisper Model triggers a download (~470 MB for `small`, up to 3 GB for `large`) on first selection. We show a progress dialog **at app startup** if the model isn't cached, but the **Settings-triggered swap** uses a different code path that only shows an indeterminate spinner — no MB-downloaded indicator.

**Workaround**: watch `~/Library/Logs/Whisper-Free/whisper-free.log` for progress, or trust the spinner.

**Fix planned for v1.1**: hook HuggingFace Hub's download progress callback into the swap dialog.

---

## Cosmetic / nice-to-have for v1.x

- **Mac-native notifications** via `UNUserNotificationCenter` instead of `QSystemTrayIcon.showMessage()`
- **Sparkle auto-updater** so users don't need to manually re-download / `brew upgrade`
- **Backdrop blur** on the overlay via `NSVisualEffectView` (real frosted glass instead of solid translucent fill)
- **Designed menu bar template icon** at `assets/menu-bar-icon.png` (currently uses a Qt-drawn mic glyph fallback)
- **Square 1024×1024 app icon** (current source is 960×1088 and gets stretched slightly by `sips` into `.icns`)
- **`llvmlite` bundle bloat** — 110 MB out of 493 MB total `.app` size. Pulled in by `numba` → `librosa`. Could potentially drop `librosa` in favor of pure-`scipy` decoding to trim the bundle.

---

## Reporting bugs

`.github/ISSUE_TEMPLATE/macos-bug.md` provides the structure for new reports. Include the log from `~/Library/Logs/Whisper-Free/whisper-free.log` and your macOS version + Mac model.
