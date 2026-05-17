"""Gallery View — main photo browser with search and filters."""
import os
import subprocess
import sys

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QLineEdit, QComboBox, QMenu, QMessageBox, QInputDialog, QApplication)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal

from ui.styles import btn_style
from ui.photo_grid import PhotoGrid
from core.database import Database

PAGE_SIZE = 200


class GalleryView(QWidget):
    # emitted when user wants to add photo to album (for AlbumView to handle)
    add_to_album_requested = pyqtSignal(int)  # photo_id

    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        self._offset = 0
        self._total = 0
        self._current_query = ""
        self._current_person_id = None
        self._all_rows = []   # current loaded rows
        self._build_ui()
        self._refresh_person_filter()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        # ── Toolbar ─────────────────────────────────────────────────────────
        toolbar = QWidget()
        toolbar.setStyleSheet("QWidget { background: #0f0f0f; border-bottom: 1px solid #1e1e1e; }")
        toolbar.setFixedHeight(52)
        tbar = QHBoxLayout(toolbar)
        tbar.setContentsMargins(16, 8, 16, 8)
        tbar.setSpacing(10)

        title = QLabel("Gallery")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #c0d0e0; min-width: 80px;")
        tbar.addWidget(title)

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search by filename or camera…")
        self.search_box.setStyleSheet(
            "QLineEdit { background: #1a1a1a; color: #ccc; border: 1px solid #333; "
            "border-radius: 4px; padding: 4px 10px; font-size: 12px; }"
            "QLineEdit:focus { border-color: #4a8abf; }"
        )
        self.search_box.setFixedWidth(300)
        self.search_box.textChanged.connect(self._on_search_changed)
        tbar.addWidget(self.search_box)

        person_label = QLabel("Person:")
        person_label.setStyleSheet("color: #666; font-size: 12px;")
        tbar.addWidget(person_label)

        self.person_filter = QComboBox()
        self.person_filter.setStyleSheet(
            "QComboBox { background: #1a1a1a; color: #ccc; border: 1px solid #333; "
            "border-radius: 4px; padding: 3px 8px; font-size: 12px; min-width: 140px; }"
            "QComboBox::drop-down { border: none; }"
            "QComboBox QAbstractItemView { background: #1e1e1e; color: #ccc; "
            "selection-background-color: #2a4a6e; }"
        )
        self.person_filter.addItem("All People", None)
        self.person_filter.currentIndexChanged.connect(self._on_filter_changed)
        tbar.addWidget(self.person_filter)

        tbar.addStretch()

        self.refresh_btn = QPushButton("↺  Refresh")
        self.refresh_btn.setStyleSheet(btn_style(small=True))
        self.refresh_btn.setFixedHeight(30)
        self.refresh_btn.clicked.connect(self.refresh)
        tbar.addWidget(self.refresh_btn)

        layout.addWidget(toolbar)

        # ── Status bar ───────────────────────────────────────────────────────
        self.status_label = QLabel("No photos")
        self.status_label.setStyleSheet("color: #555; font-size: 11px; padding: 4px 16px;")
        self.status_label.setFixedHeight(24)
        layout.addWidget(self.status_label)

        # ── Grid ─────────────────────────────────────────────────────────────
        self.grid = PhotoGrid()
        self.grid.photo_activated.connect(self._on_photo_activated)
        self.grid.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.grid.customContextMenuRequested.connect(self._on_context_menu)
        layout.addWidget(self.grid, 1)

        # ── Load more ────────────────────────────────────────────────────────
        self.load_more_btn = QPushButton()
        self.load_more_btn.setStyleSheet(btn_style())
        self.load_more_btn.setFixedHeight(36)
        self.load_more_btn.hide()
        self.load_more_btn.clicked.connect(self._load_more)
        layout.addWidget(self.load_more_btn)

    def _refresh_person_filter(self):
        current_pid = self.person_filter.currentData()
        self.person_filter.blockSignals(True)
        self.person_filter.clear()
        self.person_filter.addItem("All People", None)
        for p in self.db.get_all_people():
            self.person_filter.addItem(p["name"], p["id"])
        # Restore selection
        for i in range(self.person_filter.count()):
            if self.person_filter.itemData(i) == current_pid:
                self.person_filter.setCurrentIndex(i)
                break
        self.person_filter.blockSignals(False)

    def refresh(self):
        self._refresh_person_filter()
        self._offset = 0
        self._load_page(reset=True)

    def _on_search_changed(self, text: str):
        self._current_query = text.strip()
        self._offset = 0
        QTimer.singleShot(300, lambda: self._load_page(reset=True))

    def _on_filter_changed(self):
        self._current_person_id = self.person_filter.currentData()
        self._offset = 0
        self._load_page(reset=True)

    def _load_page(self, reset: bool = False):
        filters = {}
        if self._current_person_id:
            filters["person_id"] = self._current_person_id
        rows = self.db.search_photos(
            query=self._current_query,
            filters=filters if filters else None,
        )
        # Client-side paging (search_photos returns all, we page locally for now)
        if reset:
            self._all_rows = rows
            self._offset = 0
            page = self._all_rows[:PAGE_SIZE]
            self.grid.set_photos(page)
        else:
            page = self._all_rows[self._offset:self._offset + PAGE_SIZE]
            self.grid.append_photos(page)
        self._offset = min(self._offset + PAGE_SIZE, len(self._all_rows))
        total = len(self._all_rows)
        shown = min(self._offset, total)
        self.status_label.setText(
            f"Showing {shown:,} of {total:,} photo{'s' if total != 1 else ''}"
        )
        remaining = total - shown
        if remaining > 0:
            self.load_more_btn.setText(
                f"Load {min(remaining, PAGE_SIZE):,} more  ({remaining:,} remaining)"
            )
            self.load_more_btn.show()
        else:
            self.load_more_btn.hide()

    def _load_more(self):
        self._load_page(reset=False)

    def _on_photo_activated(self, photo_id: int):
        from ui.photo_detail import PhotoDetailDialog
        all_ids = self.grid.photo_ids()
        dlg = PhotoDetailDialog(self.db, photo_id, all_ids, parent=self)
        dlg.exec()

    def _on_context_menu(self, pos):
        item = self.grid.itemAt(pos)
        if not item:
            return
        photo_id = item.data(Qt.ItemDataRole.UserRole)
        row = self.db.get_photo(photo_id)
        if not row:
            return
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background: #1e1e1e; color: #ccc; border: 1px solid #333; }"
            "QMenu::item { padding: 6px 20px; }"
            "QMenu::item:selected { background: #2a4a6e; }"
        )
        act_detail = menu.addAction("\U0001f50d  View Details")
        act_add_album = menu.addAction("\U0001f5c2  Add to Album…")
        menu.addSeparator()
        act_open = menu.addAction("\U0001f4c2  Open File Location")
        act_copy = menu.addAction("\U0001f4cb  Copy Path")
        action = menu.exec(self.grid.mapToGlobal(pos))
        if action == act_detail:
            self._on_photo_activated(photo_id)
        elif action == act_add_album:
            self._add_to_album(photo_id)
        elif action == act_open:
            self._open_file_location(row["file_path"])
        elif action == act_copy:
            QApplication.clipboard().setText(row["file_path"])

    def _add_to_album(self, photo_id: int):
        albums = self.db.get_all_albums()
        if not albums:
            QMessageBox.information(self, "No Albums", "Create an album first in the Albums view.")
            return
        names = [f"{a['name']}  ({a['photo_count']} photos)" for a in albums]
        item, ok = QInputDialog.getItem(self, "Add to Album", "Select album:", names, 0, False)
        if ok and item:
            idx = names.index(item)
            album_id = albums[idx]["id"]
            self.db.add_photo_to_album(album_id, photo_id)

    def _open_file_location(self, path: str):
        folder = os.path.dirname(path)
        if sys.platform == "win32":
            os.startfile(folder)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", folder])
        else:
            subprocess.Popen(["xdg-open", folder])
