# Known Issues — macOS port (v1.0.0)

This file is the consolidated triage log for everything flagged during the
phased macOS port (Phases 1–8) that needs runtime validation or follow-up
on real Apple Silicon hardware with the full dependency stack installed.

It exists because the port was implemented in a Python 3.9 environment
without `mlx`, `PySide6`, or `pyobjc` installable. The code paths are
documented and structurally validated (AST checks, compile checks, public
API parity tests) but have not all been runtime-exercised. Treat this as
the punch list for v1.0.0 dogfooding.

Severities:
- **P0** — blocks v1.0.0 release
- **P1** — should be fixed before public announcement, but DMG can ship
- **P2** — polish / nice-to-have, fix when convenient
- **ASSET** — needs design or external work, not a code bug

---

## P0 — Must verify before announcing v1.0.0

### P0-1: PyInstaller bundles MLX Metal kernels correctly
**Phase**: 7
**Symptom on failure**: built `.app` launches but `mlx_whisper.transcribe()`
raises "metal library not found" or similar.
**How to check**:
```bash
./scripts/build_macos.sh
open dist/Whisper-Free.app
# In the app: click "Start Recording" in the status bar, speak, stop
# Check ~/Library/Logs/Whisper-Free/whisper-free.log for MLX errors
```
**If it fails**:
1. Inspect `dist/Whisper-Free.app/Contents/Resources/mlx/` — look for
   `*.metallib` files.
2. If missing, the `packaging/macos/hook-mlx.py` rglob fallback didn't
   work. Add explicit paths to the `binaries=` arg in
   `packaging/macos/Whisper-Free.spec`.
3. If that still fails, fall back to py2app per `docs/MACOS_PORT.md §6.4`
   (~2 extra days).

### P0-2: mlx-whisper transcribe() kwargs match our call
**Phase**: 2
**Symptom on failure**: PTT recording works, but transcription raises
`TypeError: transcribe() got an unexpected keyword argument 'X'`.
**How to check**:
```bash
source venv/bin/activate
python -c "
import mlx_whisper, numpy as np, inspect
print(inspect.signature(mlx_whisper.transcribe))
# Run a real call:
silent = np.zeros(int(16000 * 0.5), dtype=np.float32)
r = mlx_whisper.transcribe(silent, path_or_hf_repo='mlx-community/whisper-tiny-mlx',
                            language='en', task='transcribe', temperature=0.0, verbose=False)
print(list(r.keys()))
"
```
**If it fails**: edit `WhisperEngineMLX.transcribe()` in
`app/core/whisper_engine_mlx.py:transcribe` to match the actual signature.
One-line fix.

### P0-3: pyobjc Accessibility check works correctly
**Phase**: 4
**Symptom on failure**: onboarding wizard's Accessibility step never
auto-advances even after the user toggles the permission on.
**How to check** (after granting Accessibility manually):
```bash
source venv/bin/activate
python -c "
from app.platform.macos.hotkey_perms import is_accessibility_granted
print('Granted:', is_accessibility_granted())
"
```
**If it returns False after granting**: the `AXIsProcessTrustedWithOptions`
CoreFoundation dict creation may need adjustment. Replace with the simpler
`AXIsProcessTrusted()` no-options branch — it's already in the fallback
path in `hotkey_perms.py`, just promote it.

### P0-4: NSWindow collection behavior actually applies
**Phase**: 6
**Symptom on failure**: overlay appears only on the current Space; when
you switch Spaces or enter a full-screen app, it disappears.
**How to check**:
1. Enter full-screen in Safari (or Xcode).
2. Press hotkey to trigger recording.
3. Overlay should be visible above Safari.
4. Switch Spaces — overlay should follow.

**If it fails**: in `app/platform/macos/init.py:apply_overlay_window_behavior`,
the `objc.objc_object(c_void_p=...)` call may need a different signature.
Try `objc.objc_object(c_void_p=ctypes.c_void_p(view_ptr))`. Also check
that `widget.winId()` is non-zero when `showEvent` fires; if not, defer
the call via `QTimer.singleShot(0, ...)`.

---

## P1 — Should fix before announce, can ship without

### P1-1: Right Option hotkey may not register
**Phase**: 3
**Symptom on failure**: tapping Right Option does nothing; recording only
toggles via the menu bar icon.
**Root cause**: `pynput.keyboard.GlobalHotKeys` is designed for
modifier+key combos. Single-key hotkeys like `<alt_r>` may not fire.
**Workaround**: Open Settings → Hotkey, change to `cmd+shift+space`
(the fallback default we ship with).
**Proper fix**: extend `HotkeyManager` to use `pynput.keyboard.Listener`
for single-key tap-toggle detection when the configured hotkey has no
`+`. ~1 day of work.

### P1-2: SMAppService registration from source
**Phase**: 5
**Symptom on failure**: toggling "Open at Login" in Settings logs a
warning; login auto-launch doesn't happen.
**Expected**: this works only when running the bundled `.app` installed
to `/Applications`. From source, SMAppService refuses to register the
Python interpreter. Documented in the toggle's tooltip.
**How to verify production behavior**:
1. Build via `./scripts/build_macos.sh`.
2. Install `dist/Whisper-Free.app` to `/Applications`.
3. Toggle "Open at Login" → log out → log back in.
4. App should auto-launch.

### P1-3: First-launch Accessibility permission "double prompt"
**Phase**: 4
**Symptom**: when the user grants Accessibility in System Settings,
macOS may also show its own modal prompt the first time pynput tries
to grab a key. This is harmless but confusing.
**Workaround**: README's "First launch: grant permissions" section
explains both paths.

### P1-4: Re-grant required after binary update
**Phase**: 4
**Symptom**: after updating Whisper-Free via Homebrew, the global
hotkey stops working until the user removes + re-adds Whisper-Free
in Accessibility settings.
**Root cause**: macOS limitation — unsigned binaries change identity
on every build, so the Accessibility entry becomes stale.
**Fix**: code-sign the build with Developer ID. Requires Apple
Developer Program enrollment ($99/yr).

### P1-5: First-launch model download blocks UI
**Phase**: 2
**Symptom**: first PTT recording hangs for 30s–2min while the `small`
MLX model downloads from HuggingFace Hub. No progress UI.
**Workaround**: pre-warm by selecting the model in Settings before
first use (the model loads as a side effect).
**Proper fix**: hook HuggingFace Hub's download progress callback into
the existing `ModelLoaderWorker` pattern in `app/main.py:126`. ~0.5 day.

---

## P2 — Polish

### P2-1: Vestigial `storage.database_path` config key
**Phase**: 1
**Description**: `storage.database_path` exists in the YAML default
config but is never read by code. Misleading on Mac where it suggests
`~/.config/whisper-free/history.db` but the actual DB is in
`~/Library/Application Support/Whisper-Free/history.db`.
**Fix**: remove from `app/data/config.py` `DEFAULT_CONFIG`. (Done as
part of this Phase 9 commit — see commit log.)

### P2-2: pyobjc tuple-return shape
**Phase**: 5
**Description**: `SMAppService.registerAndReturnError_(None)` may return
either a tuple `(bool, NSError)` or a bare bool depending on pyobjc
version. `app/platform/macos/autolaunch.py` handles both shapes but the
exact dominant form should be confirmed and the alternate path removed.

### P2-3: Mac-native notifications
**Phase**: 5 (deferred to v1.x)
**Description**: We use `QSystemTrayIcon.showMessage()` for v1, which
works but isn't as polished as `UNUserNotificationCenter` (action
buttons, rich content). Deferred per design Decision 10c.

### P2-4: Sparkle auto-updater
**Phase**: 8 (deferred to v1.x)
**Description**: No in-app update mechanism. Users update via
`brew upgrade` or by re-downloading. Sparkle integration is documented
in `docs/MACOS_PORT.md` as v1.x work.

### P2-5: Wizard step skipping doesn't surface state
**Phase**: 4
**Description**: If the user clicks "Skip" on both wizard steps, they
land in a state where neither permission is granted but the app
proceeds silently. Add a banner in the menu bar popover when permissions
are missing.

---

## ASSET gaps

### A-1: `assets/menu-bar-icon.png` missing
**Phase**: 3
**Description**: Mac menu bar icons should be **template images** — pure
black/transparent PNG at 16×16 (`menu-bar-icon.png`) and 32×32
(`menu-bar-icon@2x.png`). Currently `TrayController._build_icon` falls
back to a Qt-drawn "W" placeholder.
**Fix**: have a designer produce a microphone glyph as a template image.
~1 hour.

### A-2: `assets/app-icon.png` is 960×1088 (not square)
**Phase**: 7
**Description**: `build_macos.sh` generates `app-icon.icns` from this
source via `sips`, which stretches non-square inputs. Mac icon will
look slightly distorted.
**Fix**: replace `assets/app-icon.png` with a 1024×1024 square version.
No code change needed.

### A-3: Cask SHA256 placeholder
**Phase**: 8
**Description**: `packaging/homebrew/whisper-free.rb` uses
`sha256 :no_check`. Replace with the actual SHA256 from
`dist/Whisper-Free-1.0.0.dmg.sha256` once v1.0.0 is built.

### A-4: GitHub release v1.0.0 doesn't exist yet
**Phase**: 8
**Description**: Cask URL (`releases/download/v1.0.0/Whisper-Free-1.0.0.dmg`)
points to a release that hasn't been cut. Tag v1.0.0 and upload the
DMG to make the cask installable.

---

## Workflow to clear this list

A pragmatic order to dogfood:

1. **Set up a fresh Python 3.11 venv** with `requirements-macos.txt`:
   ```bash
   python3.11 -m venv venv
   source venv/bin/activate
   pip install -r requirements-macos.txt
   ```
2. **Run from source**: `python -m app.main`. This validates Phases 1–6
   live. Triage P0-2, P0-3, P0-4, P1-1, P1-3 here.
3. **Build the bundle**: `./scripts/build_macos.sh`. Validates P0-1.
4. **Install + test**: drag `dist/Whisper-Free.app` to `/Applications`,
   right-click → Open. Validates P1-2 once installed.
5. **Cut v1.0.0**: tag, upload DMG, update cask SHA256, fix README
   funding-link wording, submit cask PR. Closes A-3, A-4.
6. **Asset polish**: commission `menu-bar-icon.png` + square
   `app-icon.png`. Closes A-1, A-2.
7. **Promote/cleanup**: file remaining P2 items as GitHub issues and
   delete this file (or move it to `docs/`).

---

## Reference

- `docs/ARCHITECTURE.md` — feature inventory.
- `docs/MACOS_PORT.md` — design decisions + per-file porting matrix.
- `docs/BUILD_MACOS.md` — dev / build / release runbook.
- (`docs/` is gitignored per project preference; the design docs live
  locally as reference.)
