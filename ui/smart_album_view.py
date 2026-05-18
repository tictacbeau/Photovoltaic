"""Smart Album View — auto-generated virtual albums driven by saved criteria."""
import json
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QSplitter, QMenu, QInputDialog,
    QMessageBox,
)
from PyQt6.QtCore import Qt

from ui.styles import btn_style
from ui.photo_grid import PhotoGrid
from ui.photo_detail import PhotoDetailDialog
from core.database import Database


class SmartAlbumView(QWidget):
    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        self._albums = []
        self._current_sa_id = None
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(0)
        root.setContentsMargins(0, 0, 0, 0)

        # ── Toolbar ──────────────────────────────────────────────────────────
        toolbar = QWidget()
        toolbar.setStyleSheet("QWidget { background: #0f0f0f; border-bottom: 1px solid #1e1e1e; }")
        toolbar.setFixedHeight(52)
        tbar = QHBoxLayout(toolbar)
        tbar.setContentsMargins(16, 8, 16, 8)
        tbar.setSpacing(10)

        title = QLabel("Smart Albums")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #c0d0e0; min-width: 120px;")
        tbar.addWidget(title)

        self.count_label = QLabel("")
        self.count_label.setStyleSheet("color: #555; font-size: 12px;")
        tbar.addWidget(self.count_label)
        tbar.addStretch()

        refresh_btn = QPushButton("↺  Refresh")
        refresh_btn.setStyleSheet(btn_style(small=True))
        refresh_btn.setFixedHeight(30)
        refresh_btn.clicked.connect(self.refresh)
        tbar.addWidget(refresh_btn)
        root.addWidget(toolbar)

        # ── Splitter ─────────────────────────────────────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setStyleSheet("QSplitter::handle { background: #1e1e1e; }")

        # Left — album list
        left = QWidget()
        left.setFixedWidth(220)
        left.setStyleSheet("background: #111;")
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.setSpacing(0)

        lbl = QLabel("  Smart Albums")
        lbl.setStyleSheet(
            "color: #555; font-size: 11px; padding: 8px 12px; "
            "border-bottom: 1px solid #1a1a1a; background: #0d0d0d;"
        )
        lbl.setFixedHeight(30)
        left_lay.addWidget(lbl)

        self.album_list = QListWidget()
        self.album_list.setStyleSheet(
            "QListWidget { background: #111; border: none; outline: none; }"
            "QListWidget::item { color: #888; font-size: 12px; padding: 10px 14px; "
            "  border-bottom: 1px solid #1a1a1a; }"
            "QListWidget::item:selected { background: #152535; color: #b0d0f0; }"
            "QListWidget::item:hover { background: #161616; }"
        )
        self.album_list.currentRowChanged.connect(self._on_album_selected)
        self.album_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.album_list.customContextMenuRequested.connect(self._on_context_menu)
        left_lay.addWidget(self.album_list, 1)
        splitter.addWidget(left)

        # Right — grid + header
        right = QWidget()
        right.setStyleSheet("background: #141414;")
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(0, 0, 0, 0)
        right_lay.setSpacing(0)

        self.header_bar = QWidget()
        self.header_bar.setStyleSheet("background: #0d0d0d; border-bottom: 1px solid #1e1e1e;")
        self.header_bar.setFixedHeight(46)
        hbar = QHBoxLayout(self.header_bar)
        hbar.setContentsMargins(20, 0, 16, 0)
        hbar.setSpacing(12)

        self.header_lbl = QLabel()
        self.header_lbl.setStyleSheet("font-size: 15px; font-weight: bold; color: #c0d0e0;")
        hbar.addWidget(self.header_lbl, 1)

        self.photo_count_lbl = QLabel()
        self.photo_count_lbl.setStyleSheet("color: #555; font-size: 11px;")
        hbar.addWidget(self.photo_count_lbl)

        self.header_bar.hide()
        right_lay.addWidget(self.header_bar)

        self.grid = PhotoGrid()
        self.grid.photo_activated.connect(self._on_photo_activated)
        right_lay.addWidget(self.grid, 1)
        splitter.addWidget(right)

        root.addWidget(splitter, 1)

    # ── Public ───────────────────────────────────────────────────────────────

    def refresh(self):
        self.db.ensure_builtin_smart_albums()
        self._albums = self.db.get_all_smart_albums()
        n = len(self._albums)
        self.count_label.setText(
            f"{n} smart album{'s' if n != 1 else ''}" if n else ""
        )
        prev_id = self._current_sa_id
        self.album_list.blockSignals(True)
        self.album_list.clear()
        for a in self._albums:
            crit = {}
            try:
                crit = json.loads(a["criteria"])
            except Exception:
                pass
            item = QListWidgetItem(f"{a['icon']}  {a['name']}")
            item.setData(Qt.ItemDataRole.UserRole, a["id"])
            item.setData(Qt.ItemDataRole.UserRole + 1, bool(a["is_builtin"]))
            self.album_list.addItem(item)
        self.album_list.blockSignals(False)

        # Restore selection
        if prev_id:
            for i in range(self.album_list.count()):
                if self.album_list.item(i).data(Qt.ItemDataRole.UserRole) == prev_id:
                    self.album_list.setCurrentRow(i)
                    return
        if self._albums:
            self.album_list.setCurrentRow(0)

    # ── Internal ─────────────────────────────────────────────────────────────

    def _on_album_selected(self, row: int):
        if row < 0 or row >= len(self._albums):
            return
        sa_id = self.album_list.item(row).data(Qt.ItemDataRole.UserRole)
        if sa_id is None:
            return
        self._current_sa_id = sa_id
        self._load_album(sa_id)

    def _load_album(self, sa_id: int):
        row = next((a for a in self._albums if a["id"] == sa_id), None)
        if not row:
            return
        photos = self.db.get_smart_album_photos(sa_id)
        self.grid.set_photos(photos)
        self.header_lbl.setText(f"{row['icon']}  {row['name']}")
        n = len(photos)
        self.photo_count_lbl.setText(f"{n:,} photo{'s' if n != 1 else ''}")
        self.header_bar.show()

    def _on_photo_activated(self, photo_id: int):
        all_ids = self.grid.photo_ids()
        dlg = PhotoDetailDialog(self.db, photo_id, all_ids, parent=self)
        dlg.exec()

    def _on_context_menu(self, pos):
        item = self.album_list.itemAt(pos)
        if not item:
            return
        sa_id = item.data(Qt.ItemDataRole.UserRole)
        is_builtin = item.data(Qt.ItemDataRole.UserRole + 1)
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background: #1e1e1e; color: #ccc; border: 1px solid #333; }"
            "QMenu::item { padding: 6px 20px; }"
            "QMenu::item:selected { background: #2a4a6e; }"
        )
        act_rename = menu.addAction("✏ Rename")
        act_delete = menu.addAction("🗑 Delete")
        if is_builtin:
            act_rename.setEnabled(False)
            act_delete.setEnabled(False)
        action = menu.exec(self.album_list.mapToGlobal(pos))
        if action == act_rename:
            self._rename(sa_id)
        elif action == act_delete:
            self._delete(sa_id)

    def _rename(self, sa_id: int):
        row = next((a for a in self._albums if a["id"] == sa_id), None)
        if not row:
            return
        name, ok = QInputDialog.getText(self, "Rename Smart Album", "Name:", text=row["name"])
        if ok and name.strip():
            self.db.update_smart_album(sa_id, name=name.strip())
            self.refresh()

    def _delete(self, sa_id: int):
        reply = QMessageBox.question(
            self, "Delete Smart Album",
            "Delete this smart album? Photos are not affected.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.db.delete_smart_album(sa_id)
            self._current_sa_id = None
            self.refresh()
