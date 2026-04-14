"""
Main window for LUFS Normalizer v3.0.

PySide6 replacement for the CustomTkinter GUI, with feature parity
plus new tabs for watch folder mode.
"""

import sys
import os
from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QCheckBox, QComboBox, QRadioButton,
    QProgressBar, QFileDialog, QMessageBox, QTabWidget, QScrollArea,
    QFrame
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QIcon, QGuiApplication

from .. import VERSION
from ..config import load_config, save_config
from ..core.presets import (
    LUFS_PRESETS, DEFAULT_FAVORITES,
    apply_lufs_preset, get_preset_for_lufs, get_preset_info
)
from .widgets import SpinnerEntry, PresetButton
from .worker import BatchWorker
from .log_dialog import LogDialog
from .about_dialog import AboutDialog
from .preset_manager import PresetManagerDialog
from .watch_panel import WatchPanel


class MainWindow(QMainWindow):
    """Main application window with Batch and Watch tabs."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"LUFS Normalizer v{VERSION}")
        self.setMinimumSize(760, 700)

        # Paths
        if getattr(sys, 'frozen', False):
            self.app_dir = Path(sys.executable).parent
        else:
            self.app_dir = Path(__file__).parent.parent.parent
        self.config_file = self.app_dir / 'config.json'

        # Load config
        self.config = load_config(self.config_file)

        # State
        self.processing = False
        self.log_dialog = None
        self.log_messages = []
        self.preset_buttons = {}
        self.selected_preset = self.config.get('preset_name', None)
        self.favorite_presets = self.config.get('favorite_presets', list(DEFAULT_FAVORITES))
        self._setting_preset = False

        # Worker
        self.worker = None

        # Set icon
        self._set_icon()

        # Build UI
        self._build_ui()
        self._load_settings_to_ui()
        self._update_file_count()
        self._fit_to_content()

    def _set_icon(self):
        for name in ('taskbar_icon.ico', 'app_icon.ico', 'taskbar_icon.png'):
            icon_path = self.app_dir / name
            if icon_path.exists():
                self.setWindowIcon(QIcon(str(icon_path)))
                break

    def _build_ui(self):
        """Build the complete UI with tabs."""
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # Tab widget
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

        # Batch Processing tab
        batch_widget = QWidget()
        self.tabs.addTab(batch_widget, "Batch Processing")
        self._build_batch_tab(batch_widget)

        # Watch Folder tab
        self.watch_panel = WatchPanel(self.config)
        self.tabs.addTab(self.watch_panel, "Watch Folder")

    def _build_batch_tab(self, parent):
        """Build the batch processing tab content."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self._batch_content = QWidget()
        content = self._batch_content
        layout = QVBoxLayout(content)
        layout.setContentsMargins(15, 10, 15, 10)
        layout.setSpacing(6)

        # Title bar
        title_row = QHBoxLayout()
        title_label = QLabel("LUFS NORMALIZER")
        title_label.setFont(QFont("", 22, QFont.Bold))
        title_row.addWidget(title_label)

        version_label = QLabel(f"v{VERSION}")
        version_label.setStyleSheet("color: gray; font-size: 11px; margin-top: 8px;")
        title_row.addWidget(version_label)
        title_row.addStretch()

        about_btn = QPushButton("About")
        about_btn.setFixedSize(70, 26)
        about_btn.setStyleSheet("""
            QPushButton { background-color: #444444; color: #cccccc; font-size: 11px; border-radius: 4px; }
            QPushButton:hover { background-color: #555555; color: white; }
        """)
        about_btn.clicked.connect(self._toggle_about)
        title_row.addWidget(about_btn)
        layout.addLayout(title_row)

        # I/O Section
        io_frame = self._make_section_frame()
        io_layout = QVBoxLayout(io_frame)

        io_layout.addWidget(QLabel("Input Folder:"))
        input_row = QHBoxLayout()
        self.input_entry = QLineEdit(self.config.get('input_folder', ''))
        self.input_entry.textChanged.connect(self._update_file_count)
        input_row.addWidget(self.input_entry)
        browse_in = QPushButton("Browse")
        browse_in.setFixedWidth(70)
        browse_in.clicked.connect(self._browse_input)
        input_row.addWidget(browse_in)
        io_layout.addLayout(input_row)

        io_layout.addWidget(QLabel("Output Folder:"))
        output_row = QHBoxLayout()
        self.output_entry = QLineEdit(self.config.get('output_folder', ''))
        output_row.addWidget(self.output_entry)
        browse_out = QPushButton("Browse")
        browse_out.setFixedWidth(70)
        browse_out.clicked.connect(self._browse_output)
        output_row.addWidget(browse_out)
        io_layout.addLayout(output_row)

        layout.addWidget(io_frame)

        # Presets Section
        presets_frame = self._make_section_frame()
        presets_layout = QVBoxLayout(presets_frame)

        presets_header = QHBoxLayout()
        presets_header.addWidget(QLabel("Favorite Presets"))
        presets_mgr_btn = QPushButton("Presets Manager")
        presets_mgr_btn.setFixedSize(140, 24)
        presets_mgr_btn.setStyleSheet("background-color: #444444; font-size: 11px;")
        presets_mgr_btn.clicked.connect(self._show_preset_manager)
        presets_header.addStretch()
        presets_header.addWidget(presets_mgr_btn)
        presets_layout.addLayout(presets_header)

        self.presets_row = QHBoxLayout()
        self.presets_row.setAlignment(Qt.AlignCenter)
        presets_layout.addLayout(self.presets_row)
        self._build_favorite_buttons()

        layout.addWidget(presets_frame)

        # Settings Section (LUFS + Peak + Format)
        settings_frame = self._make_section_frame()
        settings_outer = QVBoxLayout(settings_frame)

        settings_row = QHBoxLayout()
        settings_row.setAlignment(Qt.AlignCenter)

        settings_row.addWidget(QLabel("Target LUFS:"))
        self.target_spinner = SpinnerEntry(str(self.config.get('target_lufs', -23.0)), width=70)
        self.target_spinner.valueChanged.connect(self._on_manual_entry)
        settings_row.addWidget(self.target_spinner)

        settings_row.addSpacing(20)

        settings_row.addWidget(QLabel("Peak Ceiling:"))
        self.peak_spinner = SpinnerEntry(str(self.config.get('peak_ceiling', -1.0)), width=70)
        self.peak_spinner.valueChanged.connect(self._on_manual_entry)
        settings_row.addWidget(self.peak_spinner)

        dbtp_label = QLabel("dBTP")
        dbtp_label.setStyleSheet("color: gray;")
        settings_row.addWidget(dbtp_label)

        settings_outer.addLayout(settings_row)

        format_row = QHBoxLayout()
        format_row.setAlignment(Qt.AlignCenter)

        format_row.addWidget(QLabel("Bit Depth:"))
        self.bit_depth_combo = QComboBox()
        for label, value in [('Source (preserve)', 'preserve'), ('16', '16'), ('24', '24'), ('32', '32')]:
            self.bit_depth_combo.addItem(label, value)
        self.bit_depth_combo.setCurrentIndex(
            self.bit_depth_combo.findData(self.config.get('bit_depth', 'preserve')))
        self.bit_depth_combo.setFixedWidth(160)
        self.bit_depth_combo.setStyleSheet("QComboBox { padding-right: 20px; }")
        format_row.addWidget(self.bit_depth_combo)

        format_row.addSpacing(25)

        format_row.addWidget(QLabel("Sample Rate:"))
        self.sample_rate_combo = QComboBox()
        for label, value in [('Source (preserve)', 'preserve'), ('44100 Hz', '44100 Hz'), ('48000 Hz', '48000 Hz')]:
            self.sample_rate_combo.addItem(label, value)
        self.sample_rate_combo.setCurrentIndex(
            self.sample_rate_combo.findData(self.config.get('sample_rate', 'preserve')))
        self.sample_rate_combo.setFixedWidth(170)
        self.sample_rate_combo.setStyleSheet("QComboBox { padding-right: 20px; }")
        format_row.addWidget(self.sample_rate_combo)

        settings_outer.addLayout(format_row)

        layout.addWidget(settings_frame)

        # Peak Handling Mode Section
        self.peak_mode_frame = self._make_section_frame()
        mode_layout = QVBoxLayout(self.peak_mode_frame)

        mode_label = QLabel("Peak Handling Mode")
        mode_label.setFont(QFont("", 11, QFont.Bold))
        mode_label.setStyleSheet("border: none;")
        mode_layout.addWidget(mode_label)

        strict_row = QHBoxLayout()
        self.strict_radio = QRadioButton("Strict")
        self.strict_radio.setStyleSheet("font-weight: bold; border: none;")
        self.strict_radio.setFixedWidth(80)
        self.strict_radio.toggled.connect(self._on_peak_mode_changed)
        strict_row.addWidget(self.strict_radio)
        strict_desc = QLabel("Files exceeding peak ceiling are skipped → needs_limiting/")
        strict_desc.setStyleSheet("font-size: 10px; color: gray; border: none;")
        strict_row.addWidget(strict_desc, 1)
        mode_layout.addLayout(strict_row)

        drift_row = QHBoxLayout()
        self.drift_radio = QRadioButton("Drift")
        self.drift_radio.setStyleSheet("font-weight: bold; border: none;")
        self.drift_radio.setFixedWidth(80)
        drift_row.addWidget(self.drift_radio)
        drift_desc = QLabel("Gain reduced to protect peak — LUFS may undershoot target")
        drift_desc.setStyleSheet("font-size: 10px; color: gray; border: none;")
        drift_row.addWidget(drift_desc, 1)
        mode_layout.addLayout(drift_row)

        layout.addWidget(self.peak_mode_frame)

        # Options Section
        options_frame = self._make_section_frame()
        options_outer = QVBoxLayout(options_frame)

        options_grid = QGridLayout()
        options_grid.setColumnStretch(0, 1)
        options_grid.setColumnStretch(1, 1)
        options_grid.setColumnMinimumWidth(0, 200)
        options_grid.setColumnMinimumWidth(1, 200)

        self.batch_folders_cb = QCheckBox("Batch folders")
        self.batch_folders_cb.setChecked(self.config.get('use_batch_folders', True))
        options_grid.addWidget(self.batch_folders_cb, 0, 0)

        self.auto_open_cb = QCheckBox("Auto-open output")
        self.auto_open_cb.setChecked(self.config.get('auto_open_output', True))
        options_grid.addWidget(self.auto_open_cb, 0, 1)

        self.generate_log_cb = QCheckBox("Processing log")
        self.generate_log_cb.setChecked(self.config.get('generate_log', True))
        options_grid.addWidget(self.generate_log_cb, 1, 0)

        self.generate_csv_cb = QCheckBox("CSV report")
        self.generate_csv_cb.setChecked(self.config.get('generate_csv', True))
        options_grid.addWidget(self.generate_csv_cb, 1, 1)

        self.embed_bwf_cb = QCheckBox("BWF metadata (BEXT + iXML)")
        self.embed_bwf_cb.setChecked(self.config.get('embed_bwf', False))
        options_grid.addWidget(self.embed_bwf_cb, 2, 0)

        options_outer.addLayout(options_grid)

        parallel_row = QHBoxLayout()
        parallel_row.setSpacing(4)
        self.parallel_cb = QCheckBox("Parallel Workers:")
        self.parallel_cb.setChecked(self.config.get('parallel_processing', False))
        parallel_row.addWidget(self.parallel_cb)
        self.workers_combo = QComboBox()
        self.workers_combo.addItems(['Auto'] + [str(i) for i in range(1, (os.cpu_count() or 4) + 1)])
        workers_val = self.config.get('parallel_workers', 0)
        if workers_val == 0:
            self.workers_combo.setCurrentText('Auto')
        else:
            self.workers_combo.setCurrentText(str(workers_val))
        self.workers_combo.setFixedWidth(85)
        self.workers_combo.setStyleSheet("QComboBox { padding-right: 20px; }")
        parallel_row.addWidget(self.workers_combo)
        parallel_row.addStretch()
        options_outer.addLayout(parallel_row)

        layout.addWidget(options_frame)

        # Process Section
        process_frame = self._make_section_frame()
        process_layout = QVBoxLayout(process_frame)
        process_layout.setAlignment(Qt.AlignCenter)

        file_info_row = QHBoxLayout()
        file_info_row.setAlignment(Qt.AlignCenter)
        self.file_count_label = QLabel("0 files found")
        self.file_count_label.setStyleSheet("font-size: 11px;")
        file_info_row.addWidget(self.file_count_label)
        file_info_row.addSpacing(8)
        self.mode_badge = QLabel("STRICT")
        file_info_row.addWidget(self.mode_badge)
        process_layout.addLayout(file_info_row)

        self.progress_bar = QProgressBar()
        self.progress_bar.setFixedWidth(450)
        self.progress_bar.setValue(0)
        self.progress_bar.setAlignment(Qt.AlignCenter)
        process_layout.addWidget(self.progress_bar, alignment=Qt.AlignCenter)

        self.status_label = QLabel("Ready")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("font-size: 11px;")
        process_layout.addWidget(self.status_label)

        btn_row = QHBoxLayout()
        btn_row.setAlignment(Qt.AlignCenter)

        self.start_btn = QPushButton("Start Processing")
        self.start_btn.setFixedSize(180, 38)
        self.start_btn.setStyleSheet("""
            QPushButton { background-color: #2d8f2d; font-weight: bold; font-size: 13px; }
            QPushButton:hover { background-color: #1f6b1f; }
            QPushButton:disabled { background-color: #555555; }
        """)
        self.start_btn.clicked.connect(self._start_processing)
        btn_row.addWidget(self.start_btn)

        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setFixedSize(80, 38)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setStyleSheet("""
            QPushButton { background-color: #8f2d2d; font-weight: bold; }
            QPushButton:hover { background-color: #6b1f1f; }
            QPushButton:disabled { background-color: #555555; }
        """)
        self.stop_btn.clicked.connect(self._stop_processing)
        btn_row.addWidget(self.stop_btn)

        self.log_btn = QPushButton("Log")
        self.log_btn.setFixedSize(70, 38)
        self.log_btn.setStyleSheet("background-color: #555555;")
        self.log_btn.clicked.connect(self._toggle_log)
        btn_row.addWidget(self.log_btn)

        process_layout.addLayout(btn_row)
        layout.addWidget(process_frame)

        # Footer
        from ..core.engine import VERSION as ENGINE_VERSION
        footer = QLabel(f"Engine v{ENGINE_VERSION} | True Peak | TPDF Dither | SOXR | LRA")
        footer.setAlignment(Qt.AlignCenter)
        footer.setStyleSheet("color: gray; font-size: 10px; margin-top: 5px;")
        layout.addWidget(footer)

        layout.addStretch()

        scroll.setWidget(content)

        parent_layout = QVBoxLayout(parent)
        parent_layout.setContentsMargins(0, 0, 0, 0)
        parent_layout.addWidget(scroll)

    def _make_section_frame(self):
        """Create a styled section frame."""
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                background-color: #2b2b2b;
                border-radius: 8px;
                padding: 8px;
                margin-bottom: 4px;
            }
        """)
        return frame

    # ── Preset Management ──

    def _build_favorite_buttons(self):
        """Build preset buttons in the favorites row."""
        # Clear existing
        while self.presets_row.count():
            item = self.presets_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.preset_buttons.clear()

        for preset_key in self.favorite_presets:
            preset = LUFS_PRESETS.get(preset_key)
            if not preset:
                continue
            btn = PresetButton(preset['name'], preset['lufs'])
            btn.clicked.connect(lambda checked=False, p=preset_key: self._apply_preset(p))
            self.presets_row.addWidget(btn)
            self.preset_buttons[preset_key] = btn

        if self.selected_preset and self.selected_preset in self.preset_buttons:
            self._update_preset_highlights(self.selected_preset)

    def _apply_preset(self, preset_name):
        self._setting_preset = True
        lufs, peak = apply_lufs_preset(preset_name)
        self.target_spinner.setText(str(lufs))
        self.peak_spinner.setText(str(peak))
        self._update_preset_highlights(preset_name)
        self.selected_preset = preset_name
        self._setting_preset = False
        self._log_message(f"Applied preset: {preset_name} ({lufs} LUFS)")

    def _update_preset_highlights(self, selected_name):
        for name, btn in self.preset_buttons.items():
            btn.setHighlighted(name == selected_name)

    def _on_manual_entry(self):
        if self._setting_preset:
            return
        try:
            lufs_val = float(self.target_spinner.text())
            peak_val = float(self.peak_spinner.text())
            matching = get_preset_for_lufs(lufs_val, peak_val)
        except ValueError:
            matching = None

        if matching:
            self._update_preset_highlights(matching)
            self.selected_preset = matching
        else:
            for btn in self.preset_buttons.values():
                btn.setHighlighted(False)
            self.selected_preset = None

    def _show_preset_manager(self):
        dialog = PresetManagerDialog(self.favorite_presets, self)
        if dialog.exec() == PresetManagerDialog.DialogCode.Accepted:
            self.favorite_presets = dialog.get_favorites()
            selected = dialog.get_selected_key()
            if selected:
                self._apply_preset(selected)
            self._build_favorite_buttons()
            self._save_config()

    # ── File/Folder Browsing ──

    def _browse_input(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select Input Folder",
            self.input_entry.text() or str(Path.home())
        )
        if folder:
            self.input_entry.setText(folder)

    def _browse_output(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select Output Folder",
            self.output_entry.text() or str(Path.home())
        )
        if folder:
            self.output_entry.setText(folder)

    def _update_file_count(self):
        input_folder = self.input_entry.text()
        if input_folder and Path(input_folder).exists():
            input_path = Path(input_folder)
            seen = set()
            for pattern in ('*.wav', '*.WAV', '*.aiff', '*.AIFF', '*.aif', '*.AIF'):
                for f in input_path.glob(pattern):
                    seen.add(f.resolve())
            count = len(seen)
            self.file_count_label.setText(f"{count} audio files found")
            self.start_btn.setText(f"Start Processing ({count})")
            self._file_count = count
        else:
            self.file_count_label.setText("No folder selected")
            self.start_btn.setText("Start Processing")
            self._file_count = 0

    # ── Processing ──

    def _validate_inputs(self):
        input_path = self.input_entry.text()
        if not input_path or not Path(input_path).exists():
            QMessageBox.warning(self, "Error", "Please select a valid input folder.")
            return False
        if not self.output_entry.text():
            QMessageBox.warning(self, "Error", "Please select an output folder.")
            return False
        Path(self.output_entry.text()).mkdir(parents=True, exist_ok=True)
        if self._file_count == 0:
            QMessageBox.warning(self, "Error", "No audio files found in input folder.")
            return False
        try:
            float(self.target_spinner.text())
            float(self.peak_spinner.text())
        except ValueError:
            QMessageBox.warning(self, "Error", "Invalid LUFS or Peak value.")
            return False
        return True

    def _start_processing(self):
        if self.processing:
            return
        if not self._validate_inputs():
            return

        self.processing = True
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setValue(0)
        self._clear_log()
        self._save_config()

        self._log_message("=" * 50)
        self._log_message(f"LUFS NORMALIZER v{VERSION}")
        self._log_message("=" * 50)
        self._log_message(f"Target: {self.target_spinner.text()} LUFS")
        self._log_message(f"Peak Ceiling: {self.peak_spinner.text()} dBTP")
        self._log_message("-" * 50)

        # Configure worker
        self.worker = BatchWorker(self)
        self.worker.input_dir = self.input_entry.text()
        self.worker.output_dir = self.output_entry.text()
        self.worker.target_lufs = float(self.target_spinner.text())
        self.worker.peak_ceiling = float(self.peak_spinner.text())
        self.worker.bit_depth = self.bit_depth_combo.currentData()
        self.worker.sample_rate = self.sample_rate_combo.currentData()
        self.worker.use_batch_folders = self.batch_folders_cb.isChecked()
        self.worker.generate_log = self.generate_log_cb.isChecked()
        self.worker.generate_csv = self.generate_csv_cb.isChecked()
        self.worker.strict_lufs_matching = self.strict_radio.isChecked()
        self.worker.embed_bwf = self.embed_bwf_cb.isChecked()
        self.worker.parallel = self.parallel_cb.isChecked()

        workers_text = self.workers_combo.currentText()
        self.worker.max_workers = None if workers_text == 'Auto' else int(workers_text)

        self.worker.progress.connect(self._on_progress)
        self.worker.file_result.connect(self._on_file_result)
        self.worker.finished.connect(self._on_finished)
        self.worker.error.connect(self._on_error)
        self.worker.start()

    def _stop_processing(self):
        if self.worker:
            self.worker.request_stop()
        self.status_label.setText("Stopping...")
        self._log_message("Stop requested...")

    def _on_progress(self, current, total, filename):
        pct = int(current / total * 100) if total > 0 else 0
        self.progress_bar.setValue(pct)
        self.status_label.setText(f"Processing: {filename} ({current}/{total})")

    def _on_file_result(self, filename, status, details):
        if status == 'SUCCESS':
            self._log_message(f"OK {filename} | {details}")
        elif status == 'SUCCESS_UNDERSHOOT':
            self._log_message(f"OK {filename} | {details} (peak limited)")
        elif status == 'NEEDS_LIMITING':
            self._log_message(f"!! {filename} | {details}", is_error=True)
        elif status == 'SKIPPED':
            self._log_message(f"-- {filename} | {details}")
        elif status == 'BLOCKED':
            self._log_message(f"XX {filename} | {details}", is_error=True)
        elif status == 'FAILED':
            self._log_message(f"ERR {filename} | {details}", is_error=True)
        else:
            self._log_message(f"{status}: {filename}")

    def _on_finished(self, success, total, log_path, csv_path, output_path):
        self.processing = False
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.progress_bar.setValue(100)
        self.status_label.setText(f"Complete: {success}/{total} files")

        skipped = len(self.worker.normalizer.skipped_files)
        errors = len(self.worker.normalizer.errors)
        silent = len(self.worker.normalizer.skipped_silent)
        has_issues = skipped > 0 or errors > 0

        self._log_message("")
        self._log_message("=" * 50)
        self._log_message(f"COMPLETE: {success}/{total} files processed")
        if skipped > 0:
            self._log_message(f"NEEDS LIMITING: {skipped} files exceeded peak ceiling", is_error=True)
            self._log_message(f"   -> Copied to 'needs_limiting/' folder", is_error=True)
        if silent > 0:
            self._log_message(f"SKIPPED: {silent} silent/too-quiet files")
        if errors > 0:
            self._log_message(f"ERRORS: {errors} files failed", is_error=True)
        self._log_message("=" * 50)

        if has_issues:
            self._show_log()

        if self.auto_open_cb.isChecked() and output_path:
            if has_issues:
                QMessageBox.information(
                    self, "Processing Complete",
                    f"Processed {success}/{total} files.\nCheck log for issues."
                )
            self._open_folder(output_path)
        elif output_path:
            reply = QMessageBox.question(
                self, "Processing Complete",
                f"Processed {success}/{total} files.\nOpen output folder?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self._open_folder(output_path)

    def _on_error(self, error_message):
        self.processing = False
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.status_label.setText("Error occurred")
        self._log_message(f"ERROR: {error_message}", is_error=True)
        self._show_log()
        QMessageBox.critical(self, "Error", f"An error occurred:\n{error_message}")

    # ── Log Management ──

    def _log_message(self, text, is_error=False):
        self.log_messages.append({'text': text, 'is_error': is_error})
        if self.log_dialog and self.log_dialog.isVisible():
            self.log_dialog.append_message(text, is_error)

    def _clear_log(self):
        self.log_messages.clear()
        if self.log_dialog:
            self.log_dialog.clear()

    def _toggle_log(self):
        if self.log_dialog and self.log_dialog.isVisible():
            self.log_dialog.close()
            self.log_dialog = None
        else:
            self._show_log()

    def _show_log(self):
        if self.log_dialog and self.log_dialog.isVisible():
            self.log_dialog.raise_()
            return
        self.log_dialog = LogDialog(self)
        self.log_dialog.restore_messages(self.log_messages)
        self.log_dialog.show()

    # ── Dialogs ──

    def _toggle_about(self):
        dlg = AboutDialog(self)
        dlg.exec()

    def _on_peak_mode_changed(self):
        is_strict = self.strict_radio.isChecked()
        color = "#f0a500" if is_strict else "#4a9eff"
        self.peak_mode_frame.setStyleSheet(f"""
            QFrame {{
                background-color: #2b2b2b;
                border: 2px solid {color};
                border-radius: 8px;
                padding: 8px;
                margin-bottom: 4px;
            }}
        """)
        if is_strict:
            self.mode_badge.setText("STRICT")
        else:
            self.mode_badge.setText("DRIFT")
        self.mode_badge.setStyleSheet(
            f"background-color: {color}; color: black; font-weight: bold; "
            "font-size: 10px; padding: 2px 6px; border-radius: 3px;"
        )

    # ── Config ──

    def _safe_float(self, text, default):
        try:
            return float(text)
        except (ValueError, TypeError):
            return default

    def _save_config(self):
        self.config.update({
            'input_folder': self.input_entry.text(),
            'output_folder': self.output_entry.text(),
            'target_lufs': self._safe_float(self.target_spinner.text(), -23.0),
            'peak_ceiling': self._safe_float(self.peak_spinner.text(), -1.0),
            'preset_name': self.selected_preset or '',
            'favorite_presets': self.favorite_presets,
            'strict_lufs_matching': self.strict_radio.isChecked(),
            'auto_open_output': self.auto_open_cb.isChecked(),
            'bit_depth': self.bit_depth_combo.currentData(),
            'sample_rate': self.sample_rate_combo.currentData(),
            'use_batch_folders': self.batch_folders_cb.isChecked(),
            'generate_log': self.generate_log_cb.isChecked(),
            'generate_csv': self.generate_csv_cb.isChecked(),
            'embed_bwf': self.embed_bwf_cb.isChecked(),
            'parallel_processing': self.parallel_cb.isChecked(),
            'parallel_workers': 0 if self.workers_combo.currentText() == 'Auto'
                                else int(self.workers_combo.currentText()),
        })
        # Include watch panel settings
        self.config.update(self.watch_panel.get_config_updates())
        save_config(self.config, self.config_file)

    def _load_settings_to_ui(self):
        if self.config.get('strict_lufs_matching', True):
            self.strict_radio.setChecked(True)
        else:
            self.drift_radio.setChecked(True)
        self._on_peak_mode_changed()

        matching = get_preset_for_lufs(self.target_spinner.text())
        if matching:
            self._update_preset_highlights(matching)
            self.selected_preset = matching

    # ── Utilities ──

    def _fit_to_content(self):
        """Resize window to fit all content, capped by screen size."""
        # Measure actual content height + tab bar + margins
        content_h = self._batch_content.sizeHint().height()
        tab_bar_h = self.tabs.tabBar().sizeHint().height()
        chrome = 60  # title bar + frame borders
        ideal_h = content_h + tab_bar_h + chrome
        ideal_w = 780

        screen = QGuiApplication.primaryScreen()
        if screen:
            available = screen.availableGeometry()
            w = min(ideal_w, available.width() - 40)
            h = min(ideal_h, available.height() - 40)
            x = available.x() + (available.width() - w) // 2
            y = available.y() + (available.height() - h) // 2
            self.setGeometry(x, y, w, h)
        else:
            self.resize(ideal_w, ideal_h)

    def _open_folder(self, path):
        try:
            if sys.platform == 'win32':
                os.startfile(path)
            elif sys.platform == 'darwin':
                os.system(f'open "{path}"')
            else:
                os.system(f'xdg-open "{path}"')
        except Exception as e:
            self._log_message(f"Could not open folder: {e}")

    def closeEvent(self, event):
        """Handle window close: save config, stop watcher."""
        self._save_config()
        self.watch_panel.stop_if_running()
        if self.worker and self.worker.isRunning():
            self.worker.request_stop()
            self.worker.wait(3000)
        event.accept()
