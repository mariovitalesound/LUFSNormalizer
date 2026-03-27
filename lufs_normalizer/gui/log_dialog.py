"""
Processing log dialog.

Displays real-time processing log with color-coded status messages.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPlainTextEdit, QPushButton
)
from PySide6.QtGui import QFont, QTextCharFormat, QColor


class LogDialog(QDialog):
    """Processing log window with colored error text."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Processing Log")
        self.resize(650, 420)

        layout = QVBoxLayout(self)

        self.text_edit = QPlainTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setFont(QFont("Consolas", 11))
        self.text_edit.setStyleSheet("""
            QPlainTextEdit {
                background-color: #1e1e1e;
                color: #cccccc;
                border: 1px solid #333333;
            }
        """)
        layout.addWidget(self.text_edit)

        btn_layout = QHBoxLayout()
        clear_btn = QPushButton("Clear Log")
        clear_btn.clicked.connect(self.clear)
        btn_layout.addWidget(clear_btn)

        btn_layout.addStretch()

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)

        self._messages = []

    def append_message(self, text, is_error=False):
        """Append a message to the log."""
        self._messages.append({'text': text, 'is_error': is_error})

        cursor = self.text_edit.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)

        if is_error:
            fmt = QTextCharFormat()
            fmt.setForeground(QColor("#ff5555"))
            cursor.insertText(text + "\n", fmt)
        else:
            fmt = QTextCharFormat()
            fmt.setForeground(QColor("#cccccc"))
            cursor.insertText(text + "\n", fmt)

        self.text_edit.setTextCursor(cursor)
        self.text_edit.ensureCursorVisible()

    def clear(self):
        """Clear the log."""
        self._messages.clear()
        self.text_edit.clear()

    def get_messages(self):
        """Return all stored messages."""
        return list(self._messages)

    def restore_messages(self, messages):
        """Restore messages (e.g., when reopening the dialog)."""
        self.text_edit.clear()
        self._messages = list(messages)
        for msg in messages:
            cursor = self.text_edit.textCursor()
            cursor.movePosition(cursor.MoveOperation.End)
            fmt = QTextCharFormat()
            if msg['is_error']:
                fmt.setForeground(QColor("#ff5555"))
            else:
                fmt.setForeground(QColor("#cccccc"))
            cursor.insertText(msg['text'] + "\n", fmt)
        self.text_edit.setTextCursor(self.text_edit.textCursor())
        self.text_edit.ensureCursorVisible()
