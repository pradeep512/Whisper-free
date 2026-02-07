# Whisper-Free

Whisper-Free is a local, privacy-first speech-to-text desktop app with a lightweight Dynamic-Island-style overlay. It provides push-to-talk transcription, a clean UI for file transcription, and quick copy-to-clipboard workflows.

## Demo Video

![Whisper-Free Demo](assets/demo.gif)

## Screenshots

<table>
  <tr>
    <td><img src="assets/ui-history.png" width="420" alt="Transcription History"/></td>
    <td><img src="assets/ui-file-transcribe.png" width="420" alt="File Transcribe"/></td>
    <td><img src="assets/ui-batch-transcribe.png" width="420" alt="Batch File Transcription"/></td>
  </tr>
  <tr>
    <td><img src="assets/ui-settings.png" width="420" alt="Settings"/></td>
    <td><img src="assets/ui-about.png" width="420" alt="About"/></td>
    <td></td>
  </tr>
</table>

## Features

- Push-to-talk transcription with always-on-top overlay
- Live waveform + processing indicator
- Automatic clipboard copy on completion
- History panel of transcriptions
- File transcription (WAV/FLAC/OGG out of the box; MP3/M4A/WebM with ffmpeg)
- Configurable overlay position, monitor selection, and auto-dismiss timing

## Requirements

- Linux (tested on GNOME)
- Python 3.10+
- FFmpeg (required for MP3/M4A/WebM file transcription)
- Atleast 2GB VGA

## Install using git repo

```bash
# 1) Clone
git clone https://github.com/pradeep512/Whisper-free.git
cd whisper-free

# 2) Create venv
python -m venv venv
source venv/bin/activate

# 3) Install deps
pip install -r requirements.txt
```

Install ffmpeg if you plan to transcribe MP3/M4A/WebM:

```bash
sudo apt-get install ffmpeg
```

## Run

```bash
# Run directly
python -m app.main

# Or use the Makefile
make run
```

## Install CLI (`whisper` command)

```bash
make install
# Then run
whisper
```

## Wayland Note (GNOME)

On GNOME Wayland, precise overlay positioning is restricted. To keep the overlay pinned to the top-center, Whisper-Free automatically runs via XWayland when it detects Wayland.

- Default behavior on Wayland: uses XWayland for reliable positioning
- Force Wayland (for testing):

```bash
whisper --wayland
```

- Force XWayland explicitly:

```bash
whisper --xwayland
```

- Environment override:

```bash
# Always force XWayland
export WHISPER_FORCE_XWAYLAND=1

# Never force XWayland
export WHISPER_FORCE_XWAYLAND=0
```

## Hotkey Setup (GNOME)

1. Open Settings > Keyboard > Keyboard Shortcuts > Custom Shortcuts
2. Add a new shortcut:
   - Name: Whisper Toggle
   - Command: `whisper --toggle`
   - Shortcut: Ctrl+Space

This toggles recording start/stop and triggers transcription + clipboard copy.

## File Transcription

Open the "File Transcribe" tab and select an audio file. WAV/FLAC/OGG work without extra dependencies. For MP3/M4A/WebM, install ffmpeg.

See `archive/docs/README_FILE_TRANSCRIPTION.md` for detailed file transcription guidance.

## Troubleshooting

- Overlay stuck in the middle on GNOME Wayland: ensure XWayland mode is active (default). Try `whisper --xwayland`.
- MP3/M4A won't load: install ffmpeg.

## Project Layout

- `app/` main application code
- `app/ui/overlay.py` overlay UI
- `scripts/whisper` CLI entry point
- `configs/` config templates
- `assets/` optional demo video and media



## Install using AppImage (Split Parts)

Large AppImage files are provided as split parts in the GitHub Release assets.
Download all parts into the same folder, then reassemble:

```bash
cat Whisper-Free-x86_64.AppImage.part.* > Whisper-Free-x86_64.AppImage
chmod +x Whisper-Free-x86_64.AppImage
```

Optional checksum verification (if the release provides a `.sha256` file):

```bash
sha256sum -c Whisper-Free-x86_64.AppImage.sha256
```

Run the AppImage:

```bash
./Whisper-Free-x86_64.AppImage
```

### Show In App List (Desktop Menu)

To make the AppImage appear in your app list/search, create a desktop entry:

```bash
mkdir -p ~/.local/share/applications ~/.local/share/icons/hicolor/512x512/apps
cp Whisper-Free-x86_64.AppImage ~/.local/bin/whisper-free
chmod +x ~/.local/bin/whisper-free
cp assets/app-icon-512.png ~/.local/share/icons/hicolor/512x512/apps/whisper-free.png
```

Create `~/.local/share/applications/whisper-free.desktop` with:

```ini
[Desktop Entry]
Type=Application
Name=Whisper-Free
Comment=Local, privacy-first speech-to-text with overlay
Exec=/home/your-user/.local/bin/whisper-free
Icon=whisper-free
Terminal=false
Categories=AudioVideo;Utility;
StartupWMClass=Whisper-Free
```

Then refresh desktop databases:

```bash
update-desktop-database ~/.local/share/applications
gtk-update-icon-cache ~/.local/share/icons/hicolor
```

## License

MIT
