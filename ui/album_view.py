"""Album View — create and browse photo albums."""
from PyQt6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QPushButton,
    QLabel, QListWidget, QListWidgetItem, QInputDialog, QMessageBox,
    QSplitter, QMenu)
from PyQt6.QtCore import Qt
from ui.styles import btn_style
from ui.photo_grid import PhotoGrid
from core.database import Database


class AlbumView(QWidget):
    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        self._current_album_id = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        # ── Title bar ────────────────────────────────────────────────────────
        header = QWidget()
        header.setStyleSheet("background: #0f0f0f; border-bottom: 1px solid #1e1e1e;")
        header.setFixedHeight(52)
        hlay = QHBoxLayout(header)
        hlay.setContentsMargins(16, 8, 16, 8)
        title = QLabel("Albums")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #c0d0e0;")
        hlay.addWidget(title)
        hlay.addStretch()
        layout.addWidget(header)

        # ── Splitter ─────────────────────────────────────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setStyleSheet("QSplitter::handle { background: #1e1e1e; width: 1px; }")
        layout.addWidget(splitter, 1)

        # ── Left: album list ─────────────────────────────────────────────────
        left = QWidget()
        left.setStyleSheet("background: #0e0e0e;")
        left.setFixedWidth(240)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(8, 8, 8, 8)
        ll.setSpacing(6)

        new_btn = QPushButton("+ New Album")
        new_btn.setStyleSheet(btn_style(primary=True, small=True))
        new_btn.setFixedHeight(32)
        new_btn.clicked.connect(self._new_album)
        ll.addWidget(new_btn)

        self.album_list = QListWidget()
        self.album_list.setStyleSheet(
            "QListWidget { background: transparent; border: none; color: #ccc; }"
            "QListWidget::item { padding: 8px 10px; border-radius: 4px; }"
            "QListWidget::item:selected { background: #1e3a5f; }"
            "QListWidget::item:hover { background: #161616; }"
        )
        self.album_list.currentItemChanged.connect(self._on_album_selected)
        self.album_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.album_list.customContextMenuRequested.connect(self._album_context_menu)
        ll.addWidget(self.album_list, 1)
        splitter.addWidget(left)

        # ── Right: album content ─────────────────────────────────────────────
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)

        # Album header
        self.album_header = QLabel("Select an album")
        self.album_header.setStyleSheet(
            "font-size: 15px; font-weight: bold; color: #c0c8d8; "
            "padding: 12px 16px; border-bottom: 1px solid #1e1e1e; background: #0f0f0f;"
        )
        rl.addWidget(self.album_header)

        self.photo_grid = PhotoGrid()
        self.photo_grid.photo_activated.connect(self._on_photo_activated)
        self.photo_grid.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.photo_grid.customContextMenuRequested.connect(self._photo_context_menu)
        rl.addWidget(self.photo_grid, 1)

        splitter.addWidget(right)
        splitter.setSizes([240, 800])

    def refresh(self):
        self._load_albums()

    def _load_albums(self):
        self.album_list.clear()
        for a in self.db.get_all_albums():
            count = a["photo_count"]
            item = QListWidgetItem(f"\U0001f5c2  {a['name']}  ({count})")
            item.setData(Qt.ItemDataRole.UserRole, a["id"])
            item.setToolTip(a["description"] or a["name"])
            self.album_list.addItem(item)
        # Restore selection
        if self._current_album_id:
            for i in range(self.album_list.count()):
                if self.album_list.item(i).data(Qt.ItemDataRole.UserRole) == self._current_album_id:
                    self.album_list.setCurrentRow(i)
                    break

    def _on_album_selected(self, current, previous):
        if not current:
            return
        album_id = current.data(Qt.ItemDataRole.UserRole)
        self._current_album_id = album_id
        album = self.db.get_album(album_id)
        count = self.db.count_album_photos(album_id)
        self.album_header.setText(
            f"  \U0001f5c2  {album['name']}  ·  {count} photo{'s' if count != 1 else ''}"
        )
        photos = self.db.get_album_photos(album_id)
        self.photo_grid.set_photos(photos)

    def _on_photo_activated(self, photo_id: int):
        from ui.photo_detail import PhotoDetailDialog
        all_ids = self.photo_grid.photo_ids()
        dlg = PhotoDetailDialog(self.db, photo_id, all_ids, parent=self)
        dlg.exec()

    def _new_album(self):
        name, ok = QInputDialog.getText(self, "New Album", "Album name:")
        if ok and name.strip():
            self.db.create_album(name.strip())
            self._load_albums()

    def _album_context_menu(self, pos):
        item = self.album_list.itemAt(pos)
        if not item:
            return
        album_id = item.data(Qt.ItemDataRole.UserRole)
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background: #1e1e1e; color: #ccc; border: 1px solid #333; }"
            "QMenu::item { padding: 6px 20px; }"
            "QMenu::item:selected { background: #2a4a6e; }"
        )
        act_rename = menu.addAction("✏  Rename")
        act_delete = menu.addAction("🗑  Delete")
        action = menu.exec(self.album_list.mapToGlobal(pos))
        if action == act_rename:
            self._rename_album(album_id)
        elif action == act_delete:
            self._delete_album(album_id)

    def _rename_album(self, album_id: int):
        album = self.db.get_album(album_id)
        if not album:
            return
        name, ok = QInputDialog.getText(self, "Rename Album", "New name:", text=album["name"])
        if ok and name.strip():
            self.db.update_album(album_id, name=name.strip())
            self._load_albums()

    def _delete_album(self, album_id: int):
        album = self.db.get_album(album_id)
        if not album:
            return
        reply = QMessageBox.question(
            self, "Delete Album",
            f"Delete album \"{album['name']}\"?\n"
            "Photos will NOT be deleted, just removed from this album.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.db.delete_album(album_id)
            if self._current_album_id == album_id:
                self._current_album_id = None
                self.album_header.setText("Select an album")
                self.photo_grid.set_photos([])
            self._load_albums()

    def _photo_context_menu(self, pos):
        item = self.photo_grid.itemAt(pos)
        if not item or not self._current_album_id:
            return
        photo_id = item.data(Qt.ItemDataRole.UserRole)
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background: #1e1e1e; color: #ccc; border: 1px solid #333; }"
            "QMenu::item { padding: 6px 20px; }"
            "QMenu::item:selected { background: #2a4a6e; }"
        )
        act_view = menu.addAction("🔍  View Details")
        act_remove = menu.addAction("✕  Remove from Album")
        action = menu.exec(self.photo_grid.mapToGlobal(pos))
        if action == act_view:
            self._on_photo_activated(photo_id)
        elif action == act_remove:
            self.db.remove_photo_from_album(self._current_album_id, photo_id)
            self._on_album_selected(self.album_list.currentItem(), None)
