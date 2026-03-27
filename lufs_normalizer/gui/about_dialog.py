"""
About dialog showing version info, features, and credits.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QScrollArea, QWidget, QLabel, QPushButton
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from .. import VERSION


class AboutDialog(QDialog):
    """About dialog with scrollable content sections."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About LUFS Normalizer")
        self.setFixedSize(520, 620)

        layout = QVBoxLayout(self)

        # Title
        title = QLabel("LUFS Normalizer")
        title.setFont(QFont("", 22, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        version_label = QLabel(f"Version {VERSION}")
        version_label.setAlignment(Qt.AlignCenter)
        version_label.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(version_label)

        # Scrollable content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setAlignment(Qt.AlignTop)

        sections = [
            ("Purpose",
             "Professional batch audio normalization for broadcast, game audio, "
             "and streaming. Normalizes to industry-standard LUFS while respecting "
             "True Peak limits."),
            ("Key Features",
             "- LUFS normalization (ITU-R BS.1770-4)\n"
             "- True Peak measurement (dBTP)\n"
             "- Loudness Range (LRA) measurement\n"
             "- TPDF dithering\n"
             "- SOXR resampling\n"
             "- Parallel batch processing\n"
             "- BWF/iXML metadata injection\n"
             "- Watch folder mode\n"
             "- 10 presets\n"
             "- Strict LUFS or Drift (peak-protect) modes"),
            ("Standards Reference",
             "- ATSC A/85: -24 LUFS\n"
             "- EBU R128: -23 LUFS\n"
             "- ASWG-R001: -24/-18 LUFS\n"
             "- Apple Podcasts: -16 LUFS\n"
             "- Spotify/YouTube: -14 LUFS"),
            ("Peak Handling Modes",
             "Strict LUFS (default): Skip files exceeding peak. "
             "Ensures exact target LUFS.\n\n"
             "Drift Mode: Reduce gain to protect peak. "
             "Final LUFS may undershoot target."),
            ("New in v3.0",
             "- PySide6 GUI (replaces CustomTkinter)\n"
             "- Parallel processing (ProcessPoolExecutor)\n"
             "- LRA (Loudness Range) measurement\n"
             "- BWF BEXT + iXML metadata injection\n"
             "- Watch folder auto-processing"),
            ("Keyboard Shortcuts",
             "- Up/Down arrows: Adjust by 1.0\n"
             "- Shift + Up/Down: Adjust by 0.1"),
            ("Credits",
             "Developed by Mario Vitale"),
        ]

        for section_title, section_text in sections:
            heading = QLabel(section_title)
            heading.setFont(QFont("", 12, QFont.Bold))
            heading.setStyleSheet("margin-top: 8px;")
            content_layout.addWidget(heading)

            body = QLabel(section_text)
            body.setWordWrap(True)
            body.setStyleSheet("color: #cccccc; font-size: 11px;")
            content_layout.addWidget(body)

        scroll.setWidget(content)
        layout.addWidget(scroll)

        # Close button
        close_btn = QPushButton("Close")
        close_btn.setFixedWidth(90)
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn, alignment=Qt.AlignCenter)
