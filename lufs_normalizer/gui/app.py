"""
QApplication setup with dark theme and entry point.
"""

import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPalette, QColor
from PySide6.QtCore import Qt

from .main_window import MainWindow


def create_dark_palette():
    """Create a dark Fusion-style palette."""
    palette = QPalette()

    # Base colors
    palette.setColor(QPalette.Window, QColor(30, 30, 30))
    palette.setColor(QPalette.WindowText, QColor(212, 212, 212))
    palette.setColor(QPalette.Base, QColor(25, 25, 25))
    palette.setColor(QPalette.AlternateBase, QColor(40, 40, 40))
    palette.setColor(QPalette.ToolTipBase, QColor(50, 50, 50))
    palette.setColor(QPalette.ToolTipText, QColor(212, 212, 212))
    palette.setColor(QPalette.Text, QColor(212, 212, 212))
    palette.setColor(QPalette.Button, QColor(45, 45, 45))
    palette.setColor(QPalette.ButtonText, QColor(212, 212, 212))
    palette.setColor(QPalette.BrightText, QColor(255, 255, 255))
    palette.setColor(QPalette.Link, QColor(42, 130, 218))
    palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
    palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))

    # Disabled colors
    palette.setColor(QPalette.Disabled, QPalette.WindowText, QColor(127, 127, 127))
    palette.setColor(QPalette.Disabled, QPalette.Text, QColor(127, 127, 127))
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(127, 127, 127))

    return palette


DARK_STYLESHEET = """
    QWidget {
        font-size: 12px;
    }
    QMainWindow {
        background-color: #1e1e1e;
    }
    QTabWidget::pane {
        border: 1px solid #333;
        background-color: #1e1e1e;
    }
    QTabBar::tab {
        background-color: #2b2b2b;
        color: #aaa;
        padding: 8px 20px;
        border: 1px solid #333;
        border-bottom: none;
        margin-right: 2px;
    }
    QTabBar::tab:selected {
        background-color: #1e1e1e;
        color: white;
        border-bottom: 2px solid #2a82da;
    }
    QTabBar::tab:hover {
        background-color: #333;
    }
    QLineEdit {
        background-color: #2b2b2b;
        border: 1px solid #444;
        border-radius: 4px;
        padding: 4px 8px;
        color: #ddd;
    }
    QLineEdit:focus {
        border-color: #2a82da;
    }
    QPushButton {
        background-color: #3c3c3c;
        border: 1px solid #555;
        border-radius: 4px;
        padding: 4px 12px;
        color: #ddd;
    }
    QPushButton:hover {
        background-color: #4c4c4c;
    }
    QPushButton:pressed {
        background-color: #2a82da;
    }
    QPushButton:disabled {
        background-color: #2b2b2b;
        color: #666;
    }
    QCheckBox {
        spacing: 6px;
    }
    QCheckBox::indicator {
        width: 16px;
        height: 16px;
    }
    QComboBox {
        background-color: #2b2b2b;
        border: 1px solid #444;
        border-radius: 4px;
        padding: 4px 8px;
        color: #ddd;
    }
    QComboBox::drop-down {
        border: none;
        width: 20px;
    }
    QComboBox QAbstractItemView {
        background-color: #2b2b2b;
        border: 1px solid #444;
        color: #ddd;
        selection-background-color: #2a82da;
    }
    QProgressBar {
        background-color: #2b2b2b;
        border: 1px solid #444;
        border-radius: 4px;
        text-align: center;
        color: #ddd;
        height: 20px;
    }
    QProgressBar::chunk {
        background-color: #2a82da;
        border-radius: 3px;
    }
    QScrollArea {
        border: none;
        background-color: transparent;
    }
    QScrollBar:vertical {
        background-color: #1e1e1e;
        width: 10px;
    }
    QScrollBar::handle:vertical {
        background-color: #444;
        border-radius: 5px;
        min-height: 20px;
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        height: 0;
    }
    QMessageBox {
        background-color: #1e1e1e;
    }
"""


def main():
    """Launch the LUFS Normalizer GUI."""
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setPalette(create_dark_palette())
    app.setStyleSheet(DARK_STYLESHEET)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == '__main__':
    main()
