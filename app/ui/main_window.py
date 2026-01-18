"""
MainWindow - Main application window with sidebar navigation

Provides the main UI for Whisper-Free with:
- Sidebar navigation (History, Settings, About)
- Stacked widget for panel switching
- Status bar showing status, model, and VRAM usage
- Dark theme with modern styling
"""

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QStackedWidget,
    QListWidget, QListWidgetItem, QLabel, QStatusBar
)
from PySide6.QtCore import Signal, Qt, QSize
from PySide6.QtGui import QIcon, QFont
import logging

from app.ui.history_panel import HistoryPanel
from app.ui.settings_panel import SettingsPanel

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """
    Main application window with history and settings.
    Provides navigation between panels and status monitoring.
    """

    # Signals
    settings_changed = Signal()  # Emitted when user saves settings

    def __init__(self, db_manager, config_manager):
        """
        Initialize main window

        Args:
            db_manager: DatabaseManager instance
            config_manager: ConfigManager instance
        """
        super().__init__()
        self.db = db_manager
        self.config = config_manager

        # Store panels
        self.history_panel = None
        self.settings_panel = None
        self.about_panel = None

        # Status bar labels
        self.status_label = None
        self.model_label = None
        self.vram_label = None

        self.setWindowTitle("Whisper-Free")
        self.setWindowTitle("Whisper-Free")
        self.setFixedSize(800, 600)
        
        # Disable maximize button, keep close and minimize
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.CustomizeWindowHint |
            Qt.WindowType.WindowTitleHint |
            Qt.WindowType.WindowSystemMenuHint |
            Qt.WindowType.WindowMinimizeButtonHint |
            Qt.WindowType.WindowCloseButtonHint
        )

        self._setup_ui()
        self._apply_theme()
        self._load_history()

        logger.info("MainWindow initialized")

    def _setup_ui(self):
        """Create sidebar, panels, status bar"""
        # Central widget with horizontal layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Sidebar navigation
        self.sidebar = QListWidget()
        self.sidebar.setFixedWidth(150)
        self.sidebar.setSpacing(4)
        self.sidebar.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        # Add sidebar items
        items = ["History", "Settings", "About"]
        for item_text in items:
            item = QListWidgetItem(item_text)
            item.setSizeHint(QSize(140, 45))
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.sidebar.addItem(item)

        # Connect sidebar selection
        self.sidebar.currentRowChanged.connect(self._on_sidebar_changed)
        
        # Add spacing for About button (a bit of a hack with QListWidget)
        # We'll just rely on the order for now, or we could add a spacer item
        # but custom widgets in QListWidget are tricky without full delegates.
        # User requested "About... into middle also as well".
        # Let's try to set a custom size for the item before About?
        # Or just leave it as is but cleaner. The request "About... into middle"
        # is vague. Let's assume they want it separated. 
        # I'll add a dummy spacer item.
        
        spacer_item = QListWidgetItem("")
        spacer_item.setFlags(Qt.ItemFlag.NoItemFlags) # Non-selectable
        spacer_item.setSizeHint(QSize(140, 20)) # Spacer height
        self.sidebar.insertItem(2, spacer_item) # Insert before About (index 2 was About)
        
        # Re-add About (it will be index 3 now)
        # Actually, "About" was added in the loop. 
        # The loop added History(0), Settings(1), About(2).
        # We need to take item 2 and move it to 3 after spacer.
        # Or easier: Clear and re-add manually.
        
        self.sidebar.clear()
        
        # Top items
        for text in ["History", "Settings"]:
            item = QListWidgetItem(text)
            item.setSizeHint(QSize(140, 45))
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.sidebar.addItem(item)
        # About item
        about_item = QListWidgetItem("About")
        about_item.setSizeHint(QSize(140, 45))
        about_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sidebar.addItem(about_item)

        # Stacked widget for panels
        self.stack = QStackedWidget()

        # Create panels
        self.history_panel = HistoryPanel(self.db)
        self.settings_panel = SettingsPanel(self.config)
        self.about_panel = self._create_about_panel()

        # Add panels to stack
        self.stack.addWidget(self.history_panel)
        self.stack.addWidget(self.settings_panel)
        self.stack.addWidget(self.about_panel)

        # Connect settings panel signals
        self.settings_panel.settings_saved.connect(self.settings_changed.emit)

        # Add to main layout
        main_layout.addWidget(self.sidebar)
        main_layout.addWidget(self.stack, 1)  # Stretch factor 1
        
        # Select History by default (Now safe to trigger signal)
        self.sidebar.setCurrentRow(0)

        # Status bar
        self._setup_status_bar()

    def _create_about_panel(self) -> QWidget:
        """Create the About panel with app information"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # App name
        title = QLabel("Whisper-Free")
        title.setStyleSheet("font-size: 32px; font-weight: bold; color: #ffffff;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Version
        version = QLabel("Version 1.0.0")
        version.setStyleSheet("font-size: 16px; color: #888888; margin-top: 8px;")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Description
        description = QLabel(
            "Local voice dictation powered by OpenAI Whisper.\n"
            "Fast, private, and completely offline.\n\n"
            "Press your hotkey to start recording,\n"
            "speak naturally, and get instant transcription."
        )
        description.setStyleSheet("font-size: 14px; color: #cccccc; margin-top: 16px;")
        description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        description.setWordWrap(True)

        # License
        license_label = QLabel("MIT License")
        license_label.setStyleSheet("font-size: 12px; color: #666666; margin-top: 24px;")
        license_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(title)
        layout.addWidget(version)
        layout.addWidget(description)
        layout.addWidget(license_label)
        layout.addStretch()

        return widget

    def _setup_status_bar(self):
        """Create status bar with status, model, and VRAM display"""
        status_bar = QStatusBar()
        self.setStatusBar(status_bar)

        # Status label
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: #00ff00; font-weight: bold;")

        # Model label
        model_name = self.config.get('whisper.model', 'small')
        self.model_label = QLabel(f"Model: {model_name}")
        self.model_label.setStyleSheet("color: #cccccc; margin-left: 16px;")

        # VRAM label
        self.vram_label = QLabel("VRAM: N/A")
        self.vram_label.setStyleSheet("color: #cccccc; margin-left: 16px;")

        # Add to status bar
        # Use permanent widgets for Right-aligned system info to avoid overlap
        
        # Spacer to push status to left and others to right
        # Default behavior: addWidget puts on left, addPermanent on right.
        
        status_bar.addWidget(self.status_label)
        
        # Create container for right side stats
        stats_widget = QWidget()
        stats_layout = QHBoxLayout(stats_widget)
        stats_layout.setContentsMargins(0, 0, 0, 0)
        stats_layout.setSpacing(16)
        
        stats_layout.addWidget(self.model_label)
        stats_layout.addWidget(self.vram_label)
        
        status_bar.addPermanentWidget(stats_widget)

    def _on_sidebar_changed(self, row: int):
        """Handle sidebar selection change"""
        # Map row index to stack index
        # Rows: 0=History, 1=Settings, 2=Spacer, 3=About
        
        if row == 0: # History
            self.stack.setCurrentIndex(0)
        elif row == 1: # Settings
            self.stack.setCurrentIndex(1)
        elif row == 2: # About
            self.stack.setCurrentIndex(2)

        logger.debug(f"Sidebar changed to row {row}, stack index {self.stack.currentIndex()}")

    def add_transcription(self, text: str, duration: float, language: str, model: str):
        """
        Add new transcription to history view

        Args:
            text: Transcription text
            duration: Recording duration in seconds
            language: Detected language code
            model: Whisper model used
        """
        try:
            # Add to database
            transcription_id = self.db.add_transcription(
                text=text,
                language=language,
                duration=duration,
                model_used=model
            )

            # Refresh history panel (it will load from database)
            self.history_panel.load_history()

            logger.info(f"Added transcription ID {transcription_id} to history")

        except Exception as e:
            logger.error(f"Failed to add transcription: {e}")

    def show_history(self):
        """Switch to history panel"""
        self.sidebar.setCurrentRow(0)
        self.stack.setCurrentIndex(0)

    def show_settings(self):
        """Switch to settings panel"""
        self.sidebar.setCurrentRow(1)
        self.stack.setCurrentIndex(1)

    def show_about(self):
        """Switch to about panel"""
        self.sidebar.setCurrentRow(2) # Index 2 now
        self.stack.setCurrentIndex(2)

    def update_status(self, message: str):
        """
        Update status bar message

        Args:
            message: Status message (e.g., "Ready", "Recording", "Processing")
        """
        # Color-code by status
        color_map = {
            "Ready": "#00ff00",
            "Recording": "#ff9900",
            "Processing": "#ffff00",
            "Error": "#ff0000"
        }

        # Determine color
        color = "#cccccc"  # Default
        for key, value in color_map.items():
                color = value
                break

        self.status_label.setText(message)
        self.status_label.setStyleSheet(f"color: {color}; font-weight: bold;")

    def update_vram_usage(self, usage_mb: float):
        """
        Update VRAM display in status bar

        Args:
            usage_mb: VRAM usage in megabytes
        """
        if usage_mb >= 1024:
            usage_gb = usage_mb / 1024
            self.vram_label.setText(f"VRAM: {usage_gb:.2f} GB")
        else:
            self.vram_label.setText(f"VRAM: {usage_mb:.0f} MB")

    def _load_history(self):
        """Load initial history from database"""
        try:
            self.history_panel.load_history()
            logger.info("Initial history loaded")
        except Exception as e:
            logger.error(f"Failed to load initial history: {e}")

    def _apply_theme(self):
        """Apply dark theme QSS styling"""
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1e1e1e;
            }

            QWidget {
                background-color: #1e1e1e;
                color: #ffffff;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                font-size: 14px;
            }

            QListWidget {
                background-color: #2d2d2d;
                border: none;
                border-right: 1px solid #3d3d3d;
                outline: none;
            }

            QListWidget::item {
                padding: 12px;
                margin: 4px 8px;
                background-color: transparent;
                border-radius: 6px;
                color: #cccccc;
            }

            QListWidget::item:selected {
                background-color: #0078d4;
                color: #ffffff;
                font-weight: bold;
            }

            QListWidget::item:hover:!selected {
                background-color: #3d3d3d;
            }

            QStatusBar {
                background-color: #252525;
                border-top: 1px solid #3d3d3d;
                color: #cccccc;
                padding: 4px;
            }

            QStatusBar QLabel {
                background-color: transparent;
                padding: 2px 8px;
            }
        """)
