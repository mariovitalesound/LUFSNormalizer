"""
Custom PySide6 widgets for LUFS Normalizer.

SpinnerEntry: QLineEdit with up/down buttons and keyboard support.
PresetButton: Two-line QPushButton with highlight state.
"""

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLineEdit, QPushButton
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QKeyEvent


class SpinnerEntry(QWidget):
    """
    Numeric entry with up/down spinner buttons.

    Features:
    - Up/Down arrow keys adjust value
    - Shift+Up/Down for fine adjustment (0.1)
    - Regular Up/Down for coarse adjustment (1.0)
    - Mouse click on arrows

    Signals:
        valueChanged(str): emitted when value changes
    """

    valueChanged = Signal(str)

    def __init__(self, initial_value="0.0", width=70, parent=None):
        super().__init__(parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self.entry = QLineEdit(initial_value)
        self.entry.setFixedWidth(width)
        self.entry.setAlignment(Qt.AlignCenter)
        self.entry.textChanged.connect(self.valueChanged.emit)
        self.entry.installEventFilter(self)
        layout.addWidget(self.entry)

        btn_layout = QVBoxLayout()
        btn_layout.setContentsMargins(0, 0, 0, 0)
        btn_layout.setSpacing(1)

        self.up_btn = QPushButton("\u25b2")
        self.up_btn.setFixedSize(24, 16)
        self.up_btn.setStyleSheet("font-size: 8px; padding: 0;")
        self.up_btn.clicked.connect(lambda: self._adjust(1.0))
        btn_layout.addWidget(self.up_btn)

        self.down_btn = QPushButton("\u25bc")
        self.down_btn.setFixedSize(24, 16)
        self.down_btn.setStyleSheet("font-size: 8px; padding: 0;")
        self.down_btn.clicked.connect(lambda: self._adjust(-1.0))
        btn_layout.addWidget(self.down_btn)

        layout.addLayout(btn_layout)

    def eventFilter(self, obj, event):
        if obj == self.entry and isinstance(event, QKeyEvent):
            if event.type() == QKeyEvent.Type.KeyPress:
                shift = event.modifiers() & Qt.ShiftModifier
                if event.key() == Qt.Key_Up:
                    self._adjust(0.1 if shift else 1.0)
                    return True
                elif event.key() == Qt.Key_Down:
                    self._adjust(-0.1 if shift else -1.0)
                    return True
        return super().eventFilter(obj, event)

    def _adjust(self, delta):
        try:
            current = float(self.entry.text())
            new_value = round(current + delta, 1)
            self.entry.setText(str(new_value))
        except ValueError:
            pass

    def text(self):
        return self.entry.text()

    def setText(self, text):
        self.entry.setText(text)

    def setReadOnly(self, readonly):
        self.entry.setReadOnly(readonly)
        self.up_btn.setEnabled(not readonly)
        self.down_btn.setEnabled(not readonly)


class PresetButton(QPushButton):
    """
    Two-line preset button with highlight state.

    Displays preset name on first line, LUFS value on second line.
    Can be highlighted when its preset matches the current settings.
    """

    def __init__(self, name, lufs_value, parent=None):
        label = f"{name}\n{int(lufs_value)} LUFS"
        super().__init__(label, parent)
        self.setFixedSize(120, 48)
        self._highlighted = False
        self._update_style()

    def setHighlighted(self, highlighted):
        self._highlighted = highlighted
        self._update_style()

    def isHighlighted(self):
        return self._highlighted

    def _update_style(self):
        if self._highlighted:
            self.setStyleSheet("""
                QPushButton {
                    background-color: #1a3d5c;
                    color: white;
                    border: 3px solid white;
                    border-radius: 6px;
                    font-size: 11px;
                    padding: 4px;
                }
                QPushButton:hover {
                    background-color: #2a4d6c;
                }
            """)
        else:
            self.setStyleSheet("""
                QPushButton {
                    background-color: #2d5a8a;
                    color: white;
                    border: 2px solid #4a7ab0;
                    border-radius: 6px;
                    font-size: 11px;
                    padding: 4px;
                }
                QPushButton:hover {
                    background-color: #3d6a9a;
                }
            """)
