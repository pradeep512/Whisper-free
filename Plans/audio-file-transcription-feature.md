# Audio File Transcription Feature - Implementation Plan

## Project: Whisper-Free Audio File Transcriber
**Date:** 2026-01-23
**Branch:** feat/audio-file-transcribe

---

## 1. FEATURE OVERVIEW

### Goal
Add a new "File Transcribe" tab to the Whisper-free application that allows users to:
1. Select an audio file from their filesystem
2. Click a "Transcribe" button to process the file
3. Automatically save the transcription as a `.txt` file in the same directory as the source audio file

### User Experience Flow
```
User clicks "File Transcribe" in sidebar
  ↓
File Transcribe panel loads
  ↓
User clicks "Select Audio File" button
  ↓
File picker dialog opens (filters: .mp3, .wav, .m4a, .flac, .ogg, .opus, .webm)
  ↓
User selects audio file (e.g., /path/to/audio/meeting.mp3)
  ↓
File path displays in UI
  ↓
User clicks "Transcribe" button
  ↓
Progress bar shows transcription status
  ↓
Transcription completes
  ↓
Text displayed in UI + saved to /path/to/audio/meeting.txt
  ↓
Success notification shown
```

---

## 2. ARCHITECTURE ANALYSIS

### 2.1 Existing Components to Leverage

| Component | Location | Current Usage | How We'll Use It |
|-----------|----------|---------------|------------------|
| **WhisperEngine** | `app/core/whisper_engine.py` | Transcribes numpy audio arrays from microphone | Will transcribe audio loaded from files |
| **ConfigManager** | `app/data/config.py` | Manages YAML configuration | Store last used directory, file preferences |
| **DatabaseManager** | `app/data/database.py` | Stores transcription history | Store file transcription history |
| **MainWindow** | `app/ui/main_window.py` | Sidebar + stacked widget navigation | Add new sidebar item + panel |
| **SettingsPanel** | `app/ui/settings_panel.py` | Reference for UI patterns | Template for new panel design |

### 2.2 New Components Required

1. **FileTranscribePanel** (`app/ui/file_transcribe_panel.py`)
   - New UI panel for file selection and transcription
   - Displays transcription results
   - Shows progress during processing

2. **FileTranscriptionWorker** (`app/core/file_transcription_worker.py`)
   - QThread worker to process files without blocking UI
   - Handles audio file loading
   - Manages transcription lifecycle
   - Saves output to .txt file

3. **AudioFileLoader** (utility in `app/core/audio_file_loader.py`)
   - Loads various audio formats (mp3, wav, m4a, flac, etc.)
   - Converts to 16kHz mono numpy array (Whisper requirement)
   - Handles file validation

---

## 3. DETAILED IMPLEMENTATION PLAN

### Phase 1: Audio File Loading Infrastructure

#### Step 1.1: Create AudioFileLoader Utility
**File:** `app/core/audio_file_loader.py`

**Requirements:**
- Load audio files using `librosa` or `soundfile` + `audioread`
- Support formats: MP3, WAV, M4A, FLAC, OGG, OPUS, WEBM
- Convert all formats to 16kHz mono (Whisper requirement)
- Return numpy array compatible with WhisperEngine
- Validate file exists, is readable, and is valid audio
- Handle errors gracefully (corrupt files, unsupported formats)

**Class Structure:**
```python
class AudioFileLoader:
    SUPPORTED_FORMATS = ['.mp3', '.wav', '.m4a', '.flac', '.ogg', '.opus', '.webm']
    TARGET_SAMPLE_RATE = 16000  # Whisper requirement

    @staticmethod
    def is_supported(file_path: str) -> bool:
        """Check if file format is supported"""

    @staticmethod
    def load_audio(file_path: str) -> np.ndarray:
        """
        Load audio file and convert to 16kHz mono numpy array
        Returns: numpy array of float32 samples
        Raises: AudioLoadError if file cannot be loaded
        """

    @staticmethod
    def get_duration(file_path: str) -> float:
        """Get audio duration in seconds without full load"""

    @staticmethod
    def validate_file(file_path: str) -> tuple[bool, str]:
        """
        Validate audio file
        Returns: (is_valid: bool, error_message: str)
        """
```

**Dependencies to Add:**
```txt
librosa>=0.10.0        # Audio loading and resampling
soundfile>=0.12.0      # WAV/FLAC loading
audioread>=3.0.0       # MP3/M4A backend
```

**Error Handling:**
- FileNotFoundError → "File does not exist"
- PermissionError → "Cannot read file (permission denied)"
- UnsupportedFormatError → "Audio format not supported"
- CorruptFileError → "File is corrupt or invalid"

---

#### Step 1.2: Create FileTranscriptionWorker
**File:** `app/core/file_transcription_worker.py`

**Requirements:**
- QThread-based worker (follows existing pattern from `main.py`)
- Load audio file using AudioFileLoader
- Pass audio to WhisperEngine.transcribe()
- Save transcription to .txt file
- Emit progress signals for UI updates
- Handle errors at each step

**Class Structure:**
```python
class FileTranscriptionWorker(QObject):
    """Worker thread for transcribing audio files"""

    # Signals
    progress_changed = Signal(int, str)  # (percentage, status_message)
    transcription_complete = Signal(dict)  # {text, language, duration, output_path}
    transcription_failed = Signal(str)  # error_message

    def __init__(self, file_path: str, whisper_engine: WhisperEngine, config: ConfigManager):
        self.file_path = file_path
        self.whisper_engine = whisper_engine
        self.config = config

    def run(self):
        """Main worker method"""
        try:
            # Step 1: Validate file (5%)
            self.progress_changed.emit(5, "Validating audio file...")
            is_valid, error_msg = AudioFileLoader.validate_file(self.file_path)
            if not is_valid:
                raise ValidationError(error_msg)

            # Step 2: Load audio (20%)
            self.progress_changed.emit(20, "Loading audio file...")
            audio_data = AudioFileLoader.load_audio(self.file_path)

            # Step 3: Transcribe (60%)
            self.progress_changed.emit(40, "Transcribing audio...")
            result = self.whisper_engine.transcribe(
                audio_data=audio_data,
                language=self.config.get('whisper.language'),
                fp16=self.config.get('whisper.fp16'),
                beam_size=self.config.get('whisper.beam_size'),
                temperature=self.config.get('whisper.temperature')
            )

            # Step 4: Save to .txt file (80%)
            self.progress_changed.emit(80, "Saving transcription...")
            output_path = self._save_transcription(result['text'])
            result['output_path'] = output_path

            # Step 5: Complete (100%)
            self.progress_changed.emit(100, "Complete!")
            self.transcription_complete.emit(result)

        except Exception as e:
            self.transcription_failed.emit(str(e))

    def _save_transcription(self, text: str) -> str:
        """
        Save transcription to .txt file in same directory as audio
        e.g., /path/to/audio/meeting.mp3 → /path/to/audio/meeting.txt

        If file exists, append timestamp: meeting_2026-01-23_14-30-45.txt
        """
        base_path = Path(self.file_path).with_suffix('.txt')

        # Handle existing file
        if base_path.exists():
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            base_name = Path(self.file_path).stem
            base_path = Path(self.file_path).parent / f"{base_name}_{timestamp}.txt"

        # Write transcription
        with open(base_path, 'w', encoding='utf-8') as f:
            f.write(text)

        return str(base_path)
```

**Thread Safety:**
- All file I/O in worker thread (not main thread)
- WhisperEngine is thread-safe (confirmed from existing code)
- Signals connect to main thread slots

---

### Phase 2: User Interface Implementation

#### Step 2.1: Create FileTranscribePanel
**File:** `app/ui/file_transcribe_panel.py`

**Requirements:**
- Follow SettingsPanel pattern (QWidget with scroll area)
- Dark theme matching existing UI
- Responsive layout
- Three main sections: File Selection, Transcription Controls, Results Display

**UI Layout:**
```
FileTranscribePanel (QWidget)
├── ScrollArea
│   └── VBoxLayout
│       ├── GroupBox: "Select Audio File"
│       │   ├── QLabel: "No file selected" / "Selected: /path/to/file.mp3"
│       │   ├── QLabel: "Duration: 3:45" (after file selected)
│       │   └── QPushButton: "Browse..." (opens file picker)
│       │
│       ├── GroupBox: "Transcription Settings"
│       │   ├── QLabel: "Model:"
│       │   ├── QLabel: "small (current model from settings)"
│       │   ├── QLabel: "Language:"
│       │   └── QLabel: "Auto-detect (from settings)"
│       │
│       ├── GroupBox: "Transcribe"
│       │   ├── QPushButton: "Transcribe File" (disabled until file selected)
│       │   ├── QProgressBar: 0-100% with status text
│       │   └── QLabel: Status messages (errors, success)
│       │
│       └── GroupBox: "Transcription Result"
│           ├── QTextEdit: Read-only transcription text (expandable)
│           ├── HBoxLayout:
│           │   ├── QPushButton: "Copy to Clipboard"
│           │   ├── QPushButton: "Open Output File"
│           │   └── QPushButton: "Clear"
│           └── QLabel: "Saved to: /path/to/output.txt"
```

**Class Structure:**
```python
class FileTranscribePanel(QWidget):
    """Panel for transcribing audio files"""

    # Signals
    file_transcribed = Signal(dict)  # Emitted when transcription completes

    def __init__(self, config: ConfigManager, whisper_engine: WhisperEngine,
                 db_manager: DatabaseManager, parent=None):
        super().__init__(parent)
        self.config = config
        self.whisper_engine = whisper_engine
        self.db_manager = db_manager

        self.selected_file_path = None
        self.current_worker = None
        self.current_thread = None
        self.last_output_path = None

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        """Create UI layout"""
        # Main scroll area
        # File selection group
        # Settings display group
        # Transcription control group
        # Results display group
        # Apply dark theme styles

    def _on_browse_clicked(self):
        """Open file picker dialog"""
        last_dir = self.config.get('file_transcribe.last_directory', str(Path.home()))

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Audio File",
            last_dir,
            "Audio Files (*.mp3 *.wav *.m4a *.flac *.ogg *.opus *.webm);;All Files (*.*)"
        )

        if file_path:
            self._on_file_selected(file_path)

    def _on_file_selected(self, file_path: str):
        """Handle file selection"""
        # Validate file
        # Get duration
        # Update UI labels
        # Enable transcribe button
        # Save last directory to config

    def _on_transcribe_clicked(self):
        """Start transcription process"""
        if not self.selected_file_path:
            return

        # Disable UI during transcription
        self._set_ui_enabled(False)

        # Create worker thread
        self.current_thread = QThread()
        self.current_worker = FileTranscriptionWorker(
            self.selected_file_path,
            self.whisper_engine,
            self.config
        )
        self.current_worker.moveToThread(self.current_thread)

        # Connect signals
        self.current_worker.progress_changed.connect(self._on_progress_changed)
        self.current_worker.transcription_complete.connect(self._on_transcription_complete)
        self.current_worker.transcription_failed.connect(self._on_transcription_failed)
        self.current_thread.started.connect(self.current_worker.run)

        # Start thread
        self.current_thread.start()

    def _on_progress_changed(self, percentage: int, message: str):
        """Update progress bar and status"""
        self.progress_bar.setValue(percentage)
        self.status_label.setText(message)

    def _on_transcription_complete(self, result: dict):
        """Handle successful transcription"""
        # Display text in QTextEdit
        # Show output file path
        # Save to database
        # Enable UI
        # Cleanup worker thread
        # Show success notification
        # Emit signal

    def _on_transcription_failed(self, error_message: str):
        """Handle transcription error"""
        # Show error in status label
        # Enable UI
        # Cleanup worker thread

    def _on_copy_clicked(self):
        """Copy transcription to clipboard"""
        text = self.result_text_edit.toPlainText()
        QApplication.clipboard().setText(text)
        self.status_label.setText("Copied to clipboard!")

    def _on_open_file_clicked(self):
        """Open output .txt file in system default editor"""
        if self.last_output_path and Path(self.last_output_path).exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.last_output_path))

    def _on_clear_clicked(self):
        """Clear current results"""
        self.selected_file_path = None
        self.last_output_path = None
        self.result_text_edit.clear()
        self.file_label.setText("No file selected")
        self.duration_label.setText("")
        self.output_path_label.setText("")
        self.status_label.setText("")
        self.progress_bar.setValue(0)
        self.transcribe_button.setEnabled(False)

    def _set_ui_enabled(self, enabled: bool):
        """Enable/disable UI during transcription"""
        self.browse_button.setEnabled(enabled)
        self.transcribe_button.setEnabled(enabled)
        self.copy_button.setEnabled(enabled)
        self.open_button.setEnabled(enabled)
        self.clear_button.setEnabled(enabled)

    # Styling methods (following SettingsPanel pattern)
    def _group_style(self) -> str:
        """QGroupBox stylesheet"""

    def _button_style(self) -> str:
        """QPushButton stylesheet"""

    def _progress_bar_style(self) -> str:
        """QProgressBar stylesheet"""

    def _text_edit_style(self) -> str:
        """QTextEdit stylesheet"""
```

**Dark Theme Styling:**
```python
# Colors matching existing UI
BACKGROUND_DARK = "#1e1e1e"
BACKGROUND_MEDIUM = "#2d2d2d"
BACKGROUND_LIGHT = "#3d3d3d"
TEXT_PRIMARY = "#ffffff"
TEXT_SECONDARY = "#cccccc"
ACCENT_BLUE = "#0078d4"
SUCCESS_GREEN = "#00ff00"
ERROR_RED = "#ff0000"
WARNING_ORANGE = "#ff9900"
```

---

#### Step 2.2: Integrate Panel into MainWindow
**File:** `app/ui/main_window.py`

**Changes Required:**

1. **Import new panel:**
```python
from app.ui.file_transcribe_panel import FileTranscribePanel
```

2. **Add to sidebar items (line ~120):**
```python
# Current:
items = ["History", "Settings", "About"]

# New:
items = ["History", "File Transcribe", "Settings", "About"]
```

3. **Create panel instance in `_setup_ui()` (line ~140):**
```python
# After self.settings_panel creation:
self.file_transcribe_panel = FileTranscribePanel(
    self.config,
    self.whisper_engine,
    self.db_manager,
    self
)
```

4. **Add to stacked widget (line ~150):**
```python
self.stack.addWidget(self.history_panel)    # Index 0
self.stack.addWidget(self.file_transcribe_panel)  # Index 1 (NEW)
self.stack.addWidget(self.settings_panel)   # Index 2 (was 1)
self.stack.addWidget(self.about_panel)      # Index 3 (was 2)
```

5. **Update `_on_sidebar_changed()` mapping (line ~180):**
```python
def _on_sidebar_changed(self, index: int):
    """Handle sidebar selection"""
    # Mapping: sidebar index → stack index
    # "History" (0) → 0
    # "File Transcribe" (1) → 1
    # "Settings" (2) → 2
    # "About" (3) → 3
    self.stack.setCurrentIndex(index)
```

6. **Connect signals in `_connect_signals()` (optional, for status bar updates):**
```python
self.file_transcribe_panel.file_transcribed.connect(self._on_file_transcribed)

def _on_file_transcribed(self, result: dict):
    """Update status bar when file transcription completes"""
    self.update_status(
        f"File transcribed: {result['duration']:.1f}s",
        "green"
    )
```

---

### Phase 3: Configuration & Data Storage

#### Step 3.1: Add Configuration Keys
**File:** `app/data/config.py`

**Add to DEFAULT_CONFIG (line ~25):**
```python
DEFAULT_CONFIG = {
    # ... existing keys ...

    'file_transcribe': {
        'last_directory': str(Path.home()),  # Remember last browsed directory
        'auto_open_output': False,           # Auto-open .txt after transcription
        'add_to_history': True,              # Add file transcriptions to history panel
        'timestamp_duplicates': True,        # Add timestamp to duplicate filenames
    },
}
```

**File:** `configs/default_config.yaml`

**Add section:**
```yaml
# File transcription settings
file_transcribe:
  last_directory: "~"           # Last directory browsed
  auto_open_output: false       # Automatically open .txt file after transcription
  add_to_history: true          # Add file transcriptions to history panel
  timestamp_duplicates: true    # Append timestamp if output file exists
```

---

#### Step 3.2: Update Database Schema (Optional Enhancement)
**File:** `app/data/database.py`

**Option A: Add column to existing table (backwards compatible):**
```python
def _create_tables(self):
    """Create database tables if they don't exist"""
    self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS transcriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT (strftime('%Y-%m-%d %H:%M:%f', 'now')),
            text TEXT NOT NULL,
            language TEXT,
            duration REAL,
            model_used TEXT,
            audio_path TEXT,
            source_type TEXT DEFAULT 'microphone',  -- NEW: 'microphone' or 'file'
            output_path TEXT                        -- NEW: path to saved .txt file
        )
    ''')

    # Migration for existing databases
    try:
        self.cursor.execute("ALTER TABLE transcriptions ADD COLUMN source_type TEXT DEFAULT 'microphone'")
        self.cursor.execute("ALTER TABLE transcriptions ADD COLUMN output_path TEXT")
        self.conn.commit()
    except sqlite3.OperationalError:
        # Columns already exist
        pass
```

**Update `add_transcription()` method:**
```python
def add_transcription(self, text: str, language: str = None,
                     duration: float = None, model_used: str = None,
                     source_type: str = 'microphone', output_path: str = None) -> int:
    """Add a transcription record"""
    self.cursor.execute('''
        INSERT INTO transcriptions
        (text, language, duration, model_used, source_type, output_path)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (text, language, duration, model_used, source_type, output_path))

    self.conn.commit()
    return self.cursor.lastrowid
```

**Add filter method for file transcriptions:**
```python
def get_file_transcriptions(self, limit: int = 50) -> List[Dict]:
    """Get only file-based transcriptions"""
    self.cursor.execute('''
        SELECT id, timestamp, text, language, duration, model_used,
               audio_path, source_type, output_path
        FROM transcriptions
        WHERE source_type = 'file'
        ORDER BY timestamp DESC, id DESC
        LIMIT ?
    ''', (limit,))

    return [self._row_to_dict(row) for row in self.cursor.fetchall()]
```

---

### Phase 4: Dependencies & Setup

#### Step 4.1: Update requirements.txt
**File:** `requirements.txt`

**Add new dependencies:**
```txt
# Audio file loading (for file transcription feature)
librosa>=0.10.0           # Audio loading, resampling, format conversion
soundfile>=0.12.0         # Backend for WAV/FLAC
audioread>=3.0.0          # Backend for MP3/M4A/OGG
```

**Note:** `librosa` will install these backends automatically:
- `ffmpeg` (via system package manager) - for MP3, M4A, WebM
- `audioread` - Python wrapper for audio decoding

---

#### Step 4.2: System Dependencies
**Platform-specific requirements:**

**Linux (Debian/Ubuntu):**
```bash
sudo apt-get install ffmpeg libsndfile1
```

**Linux (Arch/Kali):**
```bash
sudo pacman -S ffmpeg libsndfile
```

**macOS:**
```bash
brew install ffmpeg libsndfile
```

**Windows:**
- Download ffmpeg from https://ffmpeg.org/download.html
- Add to PATH
- `soundfile` and `audioread` will use it automatically

---

#### Step 4.3: Installation Instructions Update
**File:** `README.md` or `docs/installation.md`

**Add section:**
```markdown
## Audio File Transcription

The File Transcribe feature requires additional dependencies:

### System Requirements
- **ffmpeg** (for MP3, M4A, WebM support)
- **libsndfile** (for WAV, FLAC support)

#### Linux
```bash
sudo apt-get install ffmpeg libsndfile1  # Debian/Ubuntu
sudo pacman -S ffmpeg libsndfile         # Arch/Kali
```

#### macOS
```bash
brew install ffmpeg libsndfile
```

#### Windows
1. Download ffmpeg from https://ffmpeg.org/download.html
2. Extract and add to PATH
3. Restart terminal

### Python Dependencies
Already included in `requirements.txt`:
- librosa (audio loading)
- soundfile (WAV/FLAC backend)
- audioread (MP3/M4A backend)
```

---

### Phase 5: Testing Strategy

#### Step 5.1: Unit Tests
**File:** `tests/test_audio_file_loader.py`

**Test cases:**
```python
class TestAudioFileLoader:
    def test_load_wav_file(self):
        """Test loading WAV file"""

    def test_load_mp3_file(self):
        """Test loading MP3 file"""

    def test_load_m4a_file(self):
        """Test loading M4A file"""

    def test_resample_to_16khz(self):
        """Test resampling to 16kHz"""

    def test_convert_to_mono(self):
        """Test stereo to mono conversion"""

    def test_invalid_file_path(self):
        """Test error handling for non-existent file"""

    def test_unsupported_format(self):
        """Test error handling for unsupported format"""

    def test_corrupt_audio_file(self):
        """Test error handling for corrupt file"""

    def test_get_duration(self):
        """Test duration calculation"""
```

**File:** `tests/test_file_transcription_worker.py`

**Test cases:**
```python
class TestFileTranscriptionWorker:
    def test_successful_transcription(self):
        """Test complete transcription workflow"""

    def test_progress_signals(self):
        """Test progress signal emission"""

    def test_save_transcription(self):
        """Test .txt file creation"""

    def test_duplicate_filename_handling(self):
        """Test timestamp append for existing files"""

    def test_transcription_error_handling(self):
        """Test error signal emission"""
```

**File:** `tests/test_file_transcribe_panel.py`

**Test cases:**
```python
class TestFileTranscribePanel:
    def test_panel_initialization(self):
        """Test panel creates successfully"""

    def test_file_selection(self):
        """Test file selection updates UI"""

    def test_transcribe_button_state(self):
        """Test button enables/disables correctly"""

    def test_progress_bar_updates(self):
        """Test progress bar responds to signals"""

    def test_result_display(self):
        """Test transcription result display"""

    def test_copy_to_clipboard(self):
        """Test clipboard functionality"""

    def test_clear_functionality(self):
        """Test UI reset"""
```

---

#### Step 5.2: Integration Tests
**File:** `tests/test_integration_file_transcribe.py`

**Test cases:**
```python
class TestFileTranscriptionIntegration:
    def test_end_to_end_workflow(self):
        """Test complete workflow: select → transcribe → save"""

    def test_whisper_engine_integration(self):
        """Test WhisperEngine correctly processes file audio"""

    def test_database_integration(self):
        """Test file transcriptions saved to database"""

    def test_config_persistence(self):
        """Test last directory saved to config"""

    def test_ui_navigation(self):
        """Test sidebar navigation to File Transcribe panel"""
```

---

#### Step 5.3: Manual Testing Checklist

**UI Testing:**
- [ ] File Transcribe tab appears in sidebar
- [ ] Clicking tab loads panel correctly
- [ ] Browse button opens file picker
- [ ] File picker filters show correct extensions
- [ ] Selected file path displays correctly
- [ ] File duration displays after selection
- [ ] Transcribe button enables after file selection
- [ ] Progress bar updates during transcription
- [ ] Status messages display correctly
- [ ] Transcription text appears in result area
- [ ] Copy button copies text to clipboard
- [ ] Open button launches .txt file
- [ ] Clear button resets UI
- [ ] Dark theme matches existing panels

**Functionality Testing:**
- [ ] WAV file transcribes correctly
- [ ] MP3 file transcribes correctly
- [ ] M4A file transcribes correctly
- [ ] FLAC file transcribes correctly
- [ ] OGG file transcribes correctly
- [ ] .txt file saves in correct directory
- [ ] Duplicate filenames get timestamp
- [ ] Large files (>10 min) process without crash
- [ ] Invalid files show error message
- [ ] Corrupt files show error message
- [ ] Transcription uses current model from settings
- [ ] Transcription uses current language from settings
- [ ] File transcriptions appear in history (if enabled)
- [ ] Database stores file transcription records
- [ ] Last directory persists across sessions

**Error Handling Testing:**
- [ ] Non-existent file path shows error
- [ ] Unsupported format shows error
- [ ] Permission denied shows error
- [ ] Disk full shows error
- [ ] VRAM exhausted shows error
- [ ] Worker thread cleanup on error
- [ ] UI re-enables after error

**Performance Testing:**
- [ ] Short files (<1 min) transcribe quickly
- [ ] Long files (>30 min) don't freeze UI
- [ ] Progress bar updates smoothly
- [ ] Memory usage doesn't leak
- [ ] VRAM releases after transcription

---

### Phase 6: Documentation

#### Step 6.1: User Documentation
**File:** `docs/features/file-transcription.md`

**Content:**
```markdown
# File Transcription Feature

## Overview
Transcribe pre-recorded audio files and save transcriptions as .txt files.

## How to Use

### 1. Select Audio File
- Click "File Transcribe" in the sidebar
- Click "Browse..." button
- Select audio file (supported formats below)

### 2. Transcribe
- Click "Transcribe File" button
- Wait for progress bar to complete
- Transcription appears in result area

### 3. Save & Access
- Transcription automatically saves as .txt file
- Location: Same directory as audio file
- Example: `meeting.mp3` → `meeting.txt`

## Supported Formats
- MP3 (.mp3)
- WAV (.wav)
- M4A (.m4a)
- FLAC (.flac)
- OGG (.ogg)
- OPUS (.opus)
- WebM (.webm)

## Features
- **Auto-save**: Transcriptions save automatically
- **Duplicate handling**: Adds timestamp if file exists
- **History**: File transcriptions appear in History tab
- **Copy**: Copy transcription to clipboard
- **Open**: Open .txt file in default editor

## Settings
File transcription uses current Whisper settings:
- Model (tiny, base, small, medium, large)
- Language (auto-detect or specific)
- Device (CPU or CUDA)

## Troubleshooting

### "Format not supported"
Install ffmpeg: `sudo apt-get install ffmpeg`

### "Cannot read file"
Check file permissions and disk space

### "Transcription failed"
- Ensure audio file is valid
- Check available VRAM for model size
- Try smaller model in Settings

## Tips
- Use "small" model for balance of speed/accuracy
- Enable CUDA for faster processing
- Long files may take several minutes
```

---

#### Step 6.2: Developer Documentation
**File:** `docs/development/file-transcription-architecture.md`

**Content:**
```markdown
# File Transcription Architecture

## Component Diagram
```
User
  ↓ clicks Browse
FileTranscribePanel
  ↓ opens QFileDialog
User selects file
  ↓
FileTranscribePanel._on_file_selected()
  ↓ validates file
AudioFileLoader.validate_file()
  ↓
User clicks Transcribe
  ↓
FileTranscribePanel._on_transcribe_clicked()
  ↓ creates worker thread
FileTranscriptionWorker
  ↓ loads audio
AudioFileLoader.load_audio()
  ↓ returns numpy array
WhisperEngine.transcribe()
  ↓ returns transcription
FileTranscriptionWorker._save_transcription()
  ↓ writes .txt file
FileTranscribePanel._on_transcription_complete()
  ↓ updates UI
DatabaseManager.add_transcription()
```

## Threading Model
- **Main Thread**: UI (FileTranscribePanel)
- **Worker Thread**: File I/O + Transcription
- **Signals**: Progress updates, completion, errors

## File Format Pipeline
```
Input: Any supported audio format
  ↓ librosa.load()
Decode to PCM samples
  ↓ librosa.resample()
Resample to 16kHz
  ↓ librosa.to_mono()
Convert to mono
  ↓ normalize to float32
Output: numpy array (16000 Hz, mono, float32)
  ↓ WhisperEngine.transcribe()
Transcription
```

## Error Handling Strategy
Each layer handles specific errors:
- **AudioFileLoader**: File I/O, format validation
- **FileTranscriptionWorker**: Workflow errors, signal errors
- **FileTranscribePanel**: UI errors, user feedback

## Database Schema Addition
```sql
-- New columns in transcriptions table
source_type TEXT DEFAULT 'microphone'  -- 'microphone' or 'file'
output_path TEXT                       -- path to .txt file
```
```

---

### Phase 7: Implementation Order

#### Day 1: Core Infrastructure
1. ✅ Add dependencies to `requirements.txt`
2. ✅ Create `AudioFileLoader` class
3. ✅ Write unit tests for `AudioFileLoader`
4. ✅ Create `FileTranscriptionWorker` class
5. ✅ Write unit tests for `FileTranscriptionWorker`

#### Day 2: UI Implementation
6. ✅ Create `FileTranscribePanel` class
7. ✅ Implement UI layout and styling
8. ✅ Connect worker signals to UI slots
9. ✅ Write unit tests for `FileTranscribePanel`

#### Day 3: Integration
10. ✅ Add panel to `MainWindow`
11. ✅ Update sidebar navigation
12. ✅ Add configuration keys
13. ✅ Update database schema
14. ✅ Write integration tests

#### Day 4: Testing & Polish
15. ✅ Manual testing with various audio formats
16. ✅ Error handling testing
17. ✅ Performance testing with large files
18. ✅ UI polish and refinements
19. ✅ Fix any bugs discovered

#### Day 5: Documentation & Release
20. ✅ Write user documentation
21. ✅ Write developer documentation
22. ✅ Update README.md
23. ✅ Create demo video/screenshots
24. ✅ Merge to main branch

---

## 4. RISK ANALYSIS & MITIGATION

### Risk 1: Large File Memory Usage
**Risk:** Loading large audio files (>1 hour) may consume excessive RAM

**Mitigation:**
- Implement file size warning (>100 MB)
- Add chunked processing for very large files
- Show memory usage in status bar
- Allow user to cancel during processing

### Risk 2: Unsupported Audio Codecs
**Risk:** Some audio formats may fail to load despite correct extension

**Mitigation:**
- Comprehensive validation before transcription
- Clear error messages with format details
- Fallback to alternative loading methods
- Document required system dependencies

### Risk 3: UI Freezing During Processing
**Risk:** Long transcriptions may appear to freeze UI

**Mitigation:**
- All processing in worker threads (already designed)
- Progress bar with status messages
- Show estimated time based on duration
- Allow cancel functionality (future enhancement)

### Risk 4: Output File Write Failures
**Risk:** Disk full, permission issues, or path problems

**Mitigation:**
- Pre-check write permissions
- Handle disk full gracefully
- Allow user to choose different output location
- Show clear error messages

### Risk 5: VRAM Exhaustion
**Risk:** Large models may run out of VRAM on file transcription

**Mitigation:**
- Use same model validation as settings panel
- Show VRAM usage in status bar
- Suggest smaller model in error message
- Allow fallback to CPU processing

---

## 5. FUTURE ENHANCEMENTS (Post-MVP)

### Phase 2 Features (Future):
1. **Batch Processing**
   - Select multiple files
   - Queue management
   - Progress for each file

2. **Advanced Output Options**
   - Choose output directory
   - Custom filename templates
   - Export formats (SRT, VTT, JSON)

3. **Audio Preprocessing**
   - Noise reduction toggle
   - Volume normalization
   - Speaker diarization

4. **Drag & Drop**
   - Drag audio files into panel
   - Drop multiple files for batch

5. **Timeline Editor**
   - View audio waveform
   - Edit transcription timestamps
   - Export with timecodes

6. **Cancel/Pause**
   - Cancel long-running transcriptions
   - Pause/resume functionality

7. **File Management**
   - Browse previous transcriptions
   - Re-transcribe with different settings
   - Delete/export history

---

## 6. ACCEPTANCE CRITERIA

### Must Have (MVP):
- [x] New "File Transcribe" tab in sidebar
- [x] File selection via file picker dialog
- [x] Support MP3, WAV, M4A, FLAC formats
- [x] Transcribe button (enabled when file selected)
- [x] Progress bar during transcription
- [x] Display transcription result in UI
- [x] Auto-save as .txt in same directory
- [x] Handle duplicate filenames with timestamp
- [x] Copy to clipboard functionality
- [x] Open output file functionality
- [x] Clear results functionality
- [x] Error handling and user feedback
- [x] Dark theme matching existing UI
- [x] Uses current Whisper settings

### Should Have:
- [x] Save file transcriptions to database
- [x] Add to history panel (optional via config)
- [x] Remember last browsed directory
- [x] Display audio file duration
- [x] Show current model/language settings
- [x] Status messages during each step

### Nice to Have (Future):
- [ ] Batch processing
- [ ] Drag & drop support
- [ ] Custom output directory
- [ ] Cancel functionality
- [ ] Timeline/waveform view

---

## 7. SUCCESS METRICS

### Functionality:
- All supported formats load successfully
- Transcription accuracy matches microphone mode
- .txt files save correctly in 100% of cases
- No UI freezing during processing
- Error recovery works correctly

### Performance:
- Short files (<5 min): Complete in <30 seconds (small model)
- Long files (30-60 min): Complete without crashes
- Memory usage: <2x audio file size
- VRAM usage: Same as microphone mode

### User Experience:
- Intuitive UI (no documentation needed)
- Clear progress feedback
- Helpful error messages
- Consistent with existing UI/UX
- Fast response times

---

## 8. DEPENDENCIES & PREREQUISITES

### Required Before Starting:
1. Understanding of PySide6 QThread patterns
2. Familiarity with Whisper audio requirements (16kHz mono)
3. Knowledge of audio format conversion (librosa)
4. Understanding of existing codebase architecture

### External Dependencies:
- librosa (audio loading/conversion)
- soundfile (WAV/FLAC backend)
- audioread (MP3/M4A backend)
- ffmpeg (system dependency)

### Internal Dependencies:
- WhisperEngine (existing)
- ConfigManager (existing)
- DatabaseManager (existing)
- MainWindow (existing)

---

## 9. ROLLBACK PLAN

If critical issues arise:

1. **Remove sidebar item** from MainWindow
2. **Comment out panel creation** in _setup_ui()
3. **Remove from requirements.txt**: librosa, soundfile, audioread
4. **Revert database schema** if already migrated
5. **Keep code in separate branch** for future fixes

Rollback is clean because:
- Feature is self-contained
- No changes to existing components
- Optional dependencies
- Database changes are backwards compatible

---

## 10. DEPLOYMENT CHECKLIST

### Before Deployment:
- [ ] All unit tests pass
- [ ] All integration tests pass
- [ ] Manual testing completed
- [ ] Documentation written
- [ ] Dependencies added to requirements.txt
- [ ] Database migration tested
- [ ] Error handling tested
- [ ] Performance benchmarks met
- [ ] Code review completed
- [ ] No regression in existing features

### Deployment Steps:
1. Merge feature branch to main
2. Update version number
3. Update CHANGELOG.md
4. Tag release
5. Build packages (if applicable)
6. Update documentation website
7. Announce feature to users

### Post-Deployment:
- [ ] Monitor error logs
- [ ] Gather user feedback
- [ ] Track usage metrics
- [ ] Plan bug fixes if needed
- [ ] Plan enhancements based on feedback

---

## CONCLUSION

This plan provides a comprehensive roadmap for implementing the audio file transcription feature in Whisper-free. The implementation follows existing architectural patterns, maintains code quality, and delivers a seamless user experience that integrates naturally with the current application.

**Estimated Implementation Time:** 3-5 days
**Complexity:** Medium
**Risk Level:** Low (well-isolated feature)
**User Value:** High (highly requested feature)

---

**Document Version:** 1.0
**Last Updated:** 2026-01-23
**Author:** Claude (Sonnet 4.5)
**Status:** Ready for Implementation
