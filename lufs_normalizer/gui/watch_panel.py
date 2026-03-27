"""
Watch folder panel for the main window's Watch tab.

Provides controls to monitor a folder and auto-process new audio files.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QPlainTextEdit, QFileDialog, QComboBox
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QTextCharFormat, QColor

from ..core.presets import LUFS_PRESETS, apply_lufs_preset

try:
    from ..watcher.folder_watcher import FolderWatcher
    HAS_WATCHDOG = True
except ImportError:
    HAS_WATCHDOG = False


class WatchPanel(QWidget):
    """Watch folder panel with start/stop controls and activity log."""

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.config = config
        self._watcher = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)

        # Title
        title = QLabel("Watch Folder Mode")
        title.setFont(QFont("", 16, QFont.Bold))
        layout.addWidget(title)

        desc = QLabel("Automatically process audio files as they appear in a monitored folder.")
        desc.setStyleSheet("color: gray; margin-bottom: 10px;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        if not HAS_WATCHDOG:
            warn = QLabel("watchdog package not installed. Install with: pip install watchdog>=3.0.0")
            warn.setStyleSheet("color: #ff5555; font-weight: bold; margin: 20px;")
            warn.setWordWrap(True)
            layout.addWidget(warn)
            layout.addStretch()
            return

        # Watch folder
        layout.addWidget(QLabel("Watch Folder:"))
        watch_row = QHBoxLayout()
        self.watch_dir_entry = QLineEdit(config.get('watch_input_folder', ''))
        watch_row.addWidget(self.watch_dir_entry)
        browse_watch = QPushButton("Browse")
        browse_watch.setFixedWidth(70)
        browse_watch.clicked.connect(self._browse_watch)
        watch_row.addWidget(browse_watch)
        layout.addLayout(watch_row)

        # Output folder
        layout.addWidget(QLabel("Output Folder:"))
        output_row = QHBoxLayout()
        self.output_dir_entry = QLineEdit(config.get('watch_output_folder', ''))
        output_row.addWidget(self.output_dir_entry)
        browse_output = QPushButton("Browse")
        browse_output.setFixedWidth(70)
        browse_output.clicked.connect(self._browse_output)
        output_row.addWidget(browse_output)
        layout.addLayout(output_row)

        # Preset selector
        preset_row = QHBoxLayout()
        preset_row.addWidget(QLabel("Profile:"))
        self.preset_combo = QComboBox()
        for key in sorted(LUFS_PRESETS.keys()):
            preset = LUFS_PRESETS[key]
            self.preset_combo.addItem(f"{preset['name']} ({int(preset['lufs'])} LUFS)", key)
        self.preset_combo.setCurrentIndex(0)
        preset_row.addWidget(self.preset_combo)
        preset_row.addStretch()
        layout.addLayout(preset_row)

        # Start/Stop
        ctrl_row = QHBoxLayout()
        self.start_btn = QPushButton("Start Watch")
        self.start_btn.setFixedHeight(38)
        self.start_btn.setStyleSheet("background-color: #2d8f2d; font-weight: bold;")
        self.start_btn.clicked.connect(self._start_watch)
        ctrl_row.addWidget(self.start_btn)

        self.stop_btn = QPushButton("Stop Watch")
        self.stop_btn.setFixedHeight(38)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setStyleSheet("background-color: #8f2d2d; font-weight: bold;")
        self.stop_btn.clicked.connect(self._stop_watch)
        ctrl_row.addWidget(self.stop_btn)
        layout.addLayout(ctrl_row)

        # Status
        self.status_label = QLabel("Status: Idle")
        self.status_label.setStyleSheet("font-weight: bold; margin-top: 5px;")
        layout.addWidget(self.status_label)

        # Activity log
        layout.addWidget(QLabel("Activity Log:"))
        self.log_text = QPlainTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 10))
        self.log_text.setStyleSheet("""
            QPlainTextEdit {
                background-color: #1e1e1e;
                color: #cccccc;
                border: 1px solid #333;
            }
        """)
        layout.addWidget(self.log_text)

    def _browse_watch(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Watch Folder",
                                                   self.watch_dir_entry.text())
        if folder:
            self.watch_dir_entry.setText(folder)

    def _browse_output(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Output Folder",
                                                   self.output_dir_entry.text())
        if folder:
            self.output_dir_entry.setText(folder)

    def _start_watch(self):
        watch_dir = self.watch_dir_entry.text().strip()
        output_dir = self.output_dir_entry.text().strip()

        if not watch_dir or not output_dir:
            self._log_activity("Error: Please set both watch and output folders.", error=True)
            return

        preset_key = self.preset_combo.currentData()
        lufs, peak = apply_lufs_preset(preset_key)

        settings = {
            'target_lufs': lufs,
            'peak_ceiling': peak,
            'bit_depth': self.config.get('bit_depth', 'preserve'),
            'sample_rate': self.config.get('sample_rate', 'preserve'),
            'strict_lufs_matching': self.config.get('strict_lufs_matching', True),
            'embed_bwf': self.config.get('embed_bwf', False),
        }

        try:
            self._watcher = FolderWatcher(
                watch_dir=watch_dir,
                output_dir=output_dir,
                settings=settings,
                callback=self._on_file_processed,
            )
            self._watcher.start()

            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
            self.status_label.setText(f"Status: Watching {watch_dir}")
            self.status_label.setStyleSheet("font-weight: bold; color: #2d8f2d; margin-top: 5px;")
            self._log_activity(f"Started watching: {watch_dir}")
            self._log_activity(f"Preset: {preset_key} ({lufs} LUFS, {peak} dBTP)")

        except Exception as e:
            self._log_activity(f"Failed to start: {e}", error=True)

    def _stop_watch(self):
        if self._watcher:
            self._watcher.stop()
            self._watcher = None

        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.status_label.setText("Status: Idle")
        self.status_label.setStyleSheet("font-weight: bold; margin-top: 5px;")
        self._log_activity("Watch stopped.")

    def _on_file_processed(self, filename, status, result):
        """Called from watcher thread — schedule GUI update."""
        QTimer.singleShot(0, lambda: self._log_file_result(filename, status, result))

    def _log_file_result(self, filename, status, result):
        if status == 'success':
            self._log_activity(f"OK: {filename}")
        elif status == 'needs_limiting':
            self._log_activity(f"Needs limiting: {filename}", error=True)
        else:
            error_msg = result.get('error', {}).get('error', 'Unknown error') if isinstance(result, dict) else str(result)
            self._log_activity(f"Error: {filename} - {error_msg}", error=True)

    def _log_activity(self, text, error=False):
        cursor = self.log_text.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        fmt = QTextCharFormat()
        if error:
            fmt.setForeground(QColor("#ff5555"))
        else:
            fmt.setForeground(QColor("#cccccc"))
        cursor.insertText(text + "\n", fmt)
        self.log_text.setTextCursor(cursor)
        self.log_text.ensureCursorVisible()

    def get_config_updates(self):
        """Return config dict with watch panel settings."""
        return {
            'watch_input_folder': self.watch_dir_entry.text() if hasattr(self, 'watch_dir_entry') else '',
            'watch_output_folder': self.output_dir_entry.text() if hasattr(self, 'output_dir_entry') else '',
        }

    def stop_if_running(self):
        """Gracefully stop watcher if running (called on app close)."""
        if self._watcher and self._watcher.is_running():
            self._watcher.stop()
