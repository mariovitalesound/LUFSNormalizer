"""
Preset manager dialog with drag-and-drop reordering.

Allows users to manage their favorite presets (up to 5) and
reorder them via drag-and-drop in the favorites list.
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QPushButton, QAbstractItemView, QMessageBox
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from ..core.presets import LUFS_PRESETS


class PresetManagerDialog(QDialog):
    """
    Preset manager with two lists: favorites (drag-reorderable) and available.

    Signals preset changes back to the main window via accepted/rejected result.
    """

    def __init__(self, favorite_presets, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Preset Manager")
        self.resize(540, 700)

        self.favorite_presets = list(favorite_presets)
        self.selected_key = None

        layout = QVBoxLayout(self)

        # Title
        title = QLabel("Preset Manager")
        title.setFont(QFont("", 16, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        hint = QLabel("Drag to reorder favorites. Click to select.")
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet("color: gray;")
        layout.addWidget(hint)

        # Favorites section
        fav_label = QLabel("FAVORITES (Top 5 on main screen)")
        fav_label.setFont(QFont("", 11, QFont.Bold))
        layout.addWidget(fav_label)

        self.favorites_list = QListWidget()
        self.favorites_list.setDragDropMode(QAbstractItemView.InternalMove)
        self.favorites_list.setDefaultDropAction(Qt.MoveAction)
        self.favorites_list.setFixedHeight(200)
        self.favorites_list.setStyleSheet("""
            QListWidget {
                background-color: #2b2b2b;
                border: 1px solid #444;
                font-size: 12px;
            }
            QListWidget::item {
                padding: 6px;
                border-bottom: 1px solid #333;
            }
            QListWidget::item:selected {
                background-color: #2d5a8a;
            }
        """)
        self.favorites_list.itemClicked.connect(self._on_fav_clicked)
        self.favorites_list.model().rowsMoved.connect(self._on_rows_moved)
        layout.addWidget(self.favorites_list)

        # Remove from favorites button
        fav_btn_layout = QHBoxLayout()
        self.remove_btn = QPushButton("Remove from Favorites")
        self.remove_btn.setStyleSheet("background-color: #8f2d2d;")
        self.remove_btn.clicked.connect(self._remove_favorite)
        fav_btn_layout.addWidget(self.remove_btn)
        fav_btn_layout.addStretch()
        layout.addLayout(fav_btn_layout)

        # Available presets section
        avail_label = QLabel("AVAILABLE PRESETS")
        avail_label.setFont(QFont("", 11, QFont.Bold))
        layout.addWidget(avail_label)

        self.available_list = QListWidget()
        self.available_list.setStyleSheet("""
            QListWidget {
                background-color: #2b2b2b;
                border: 1px solid #444;
                font-size: 12px;
            }
            QListWidget::item {
                padding: 6px;
                border-bottom: 1px solid #333;
            }
            QListWidget::item:selected {
                background-color: #2d5a8a;
            }
        """)
        self.available_list.itemClicked.connect(self._on_avail_clicked)
        layout.addWidget(self.available_list)

        # Add to favorites button
        avail_btn_layout = QHBoxLayout()
        self.add_btn = QPushButton("Add to Favorites")
        self.add_btn.setStyleSheet("background-color: #2d8f2d;")
        self.add_btn.clicked.connect(self._add_favorite)
        avail_btn_layout.addWidget(self.add_btn)
        avail_btn_layout.addStretch()
        layout.addLayout(avail_btn_layout)

        # Bottom buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        close_btn = QPushButton("Close")
        close_btn.setFixedWidth(80)
        close_btn.setStyleSheet("background-color: #555555;")
        close_btn.clicked.connect(self.reject)
        btn_layout.addWidget(close_btn)

        apply_btn = QPushButton("Apply Selected && Close")
        apply_btn.setFixedWidth(180)
        apply_btn.setStyleSheet("background-color: #2d8f2d;")
        apply_btn.clicked.connect(self._apply_and_close)
        btn_layout.addWidget(apply_btn)

        layout.addLayout(btn_layout)

        self._refresh_lists()

    def _refresh_lists(self):
        """Rebuild both list widgets from current state."""
        self.favorites_list.clear()
        for key in self.favorite_presets:
            preset = LUFS_PRESETS.get(key, {})
            name = preset.get('name', key)
            lufs = int(preset.get('lufs', 0))
            item = QListWidgetItem(f"{name}  ({lufs} LUFS)")
            item.setData(Qt.UserRole, key)
            self.favorites_list.addItem(item)

        self.available_list.clear()
        for key in sorted(LUFS_PRESETS.keys()):
            if key not in self.favorite_presets:
                preset = LUFS_PRESETS[key]
                name = preset.get('name', key)
                lufs = int(preset.get('lufs', 0))
                desc = preset.get('description', '')
                item = QListWidgetItem(f"{name}  ({lufs} LUFS) - {desc}")
                item.setData(Qt.UserRole, key)
                self.available_list.addItem(item)

    def _on_rows_moved(self):
        """Update favorite_presets order after drag reorder."""
        new_order = []
        for i in range(self.favorites_list.count()):
            item = self.favorites_list.item(i)
            new_order.append(item.data(Qt.UserRole))
        self.favorite_presets = new_order

    def _on_fav_clicked(self, item):
        self.selected_key = item.data(Qt.UserRole)
        self.available_list.clearSelection()

    def _on_avail_clicked(self, item):
        self.selected_key = item.data(Qt.UserRole)
        self.favorites_list.clearSelection()

    def _add_favorite(self):
        """Add selected available preset to favorites."""
        items = self.available_list.selectedItems()
        if not items:
            return
        key = items[0].data(Qt.UserRole)
        if len(self.favorite_presets) >= 5:
            QMessageBox.warning(self, "Limit", "Maximum 5 favorites allowed.")
            return
        self.favorite_presets.append(key)
        self._refresh_lists()

    def _remove_favorite(self):
        """Remove selected favorite preset."""
        items = self.favorites_list.selectedItems()
        if not items:
            return
        key = items[0].data(Qt.UserRole)
        if len(self.favorite_presets) <= 1:
            QMessageBox.warning(self, "Warning", "Keep at least one favorite.")
            return
        self.favorite_presets.remove(key)
        self._refresh_lists()

    def _apply_and_close(self):
        """Accept dialog with selected preset."""
        self.accept()

    def get_favorites(self):
        """Return the current favorites list."""
        return list(self.favorite_presets)

    def get_selected_key(self):
        """Return the last selected preset key."""
        return self.selected_key
