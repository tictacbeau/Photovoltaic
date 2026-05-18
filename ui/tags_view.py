"""Tags View — browse all tags, click to see tagged photos."""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QSplitter, QMenu,
    QInputDialog, QMessageBox,
)
from PyQt6.QtCore import Qt

from ui.styles import btn_style
from ui.photo_grid import PhotoGrid
from ui.photo_detail import PhotoDetailDialog
from core.database import Database


class TagsView(QWidget):
    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        self._tags = []
        self._current_tag_id = None
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

        title = QLabel("Tags")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #c0d0e0; min-width: 60px;")
        tbar.addWidget(title)

        self.count_label = QLabel("No tags")
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

        # Left — tag list
        left = QWidget()
        left.setFixedWidth(200)
        left.setStyleSheet("background: #111;")
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.setSpacing(0)

        lbl = QLabel("  All Tags")
        lbl.setStyleSheet(
            "color: #555; font-size: 11px; padding: 8px 12px; "
            "border-bottom: 1px solid #1a1a1a; background: #0d0d0d;"
        )
        lbl.setFixedHeight(30)
        left_lay.addWidget(lbl)

        self.tag_list = QListWidget()
        self.tag_list.setStyleSheet(
            "QListWidget { background: #111; border: none; outline: none; }"
            "QListWidget::item { color: #888; font-size: 12px; padding: 8px 14px; "
            "  border-bottom: 1px solid #1a1a1a; }"
            "QListWidget::item:selected { background: #152535; color: #b0d0f0; }"
            "QListWidget::item:hover { background: #161616; }"
        )
        self.tag_list.currentRowChanged.connect(self._on_tag_selected)
        self.tag_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tag_list.customContextMenuRequested.connect(self._on_context_menu)
        left_lay.addWidget(self.tag_list, 1)
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
        self._tags = self.db.get_all_tags()
        n = len(self._tags)
        self.count_label.setText(
            f"{n} tag{'s' if n != 1 else ''}" if n else "No tags"
        )
        prev_id = self._current_tag_id
        self.tag_list.blockSignals(True)
        self.tag_list.clear()
        for t in self._tags:
            item = QListWidgetItem(f"🏷  {t['name']}  ({t['count']})")
            item.setData(Qt.ItemDataRole.UserRole, t["id"])
            self.tag_list.addItem(item)
        self.tag_list.blockSignals(False)

        # Restore selection
        if prev_id:
            for i in range(self.tag_list.count()):
                if self.tag_list.item(i).data(Qt.ItemDataRole.UserRole) == prev_id:
                    self.tag_list.setCurrentRow(i)
                    return
        if self._tags:
            self.tag_list.setCurrentRow(0)

    # ── Internal ─────────────────────────────────────────────────────────────

    def _on_tag_selected(self, row: int):
        if row < 0 or row >= len(self._tags):
            return
        tag = self._tags[row]
        self._current_tag_id = tag["id"]
        photos = self.db.search_photos(filters={"tag": tag["name"]})
        self.grid.set_photos(photos)
        n = len(photos)
        self.header_lbl.setText(f"🏷  {tag['name']}")
        self.photo_count_lbl.setText(f"{n:,} photo{'s' if n != 1 else ''}")
        self.header_bar.show()

    def _on_photo_activated(self, photo_id: int):
        all_ids = self.grid.photo_ids()
        dlg = PhotoDetailDialog(self.db, photo_id, all_ids, parent=self)
        dlg.exec()

    def _on_context_menu(self, pos):
        item = self.tag_list.itemAt(pos)
        if not item:
            return
        tag_id = item.data(Qt.ItemDataRole.UserRole)
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background: #1e1e1e; color: #ccc; border: 1px solid #333; }"
            "QMenu::item { padding: 6px 20px; }"
            "QMenu::item:selected { background: #2a4a6e; }"
        )
        act_rename = menu.addAction("✏ Rename Tag")
        act_delete = menu.addAction("🗑 Delete Tag")
        action = menu.exec(self.tag_list.mapToGlobal(pos))
        if action == act_rename:
            self._rename_tag(tag_id)
        elif action == act_delete:
            self._delete_tag(tag_id)

    def _rename_tag(self, tag_id: int):
        tag = next((t for t in self._tags if t["id"] == tag_id), None)
        if not tag:
            return
        name, ok = QInputDialog.getText(self, "Rename Tag", "New name:", text=tag["name"])
        if ok and name.strip():
            self.db.rename_tag(tag_id, name.strip())
            self.refresh()

    def _delete_tag(self, tag_id: int):
        tag = next((t for t in self._tags if t["id"] == tag_id), None)
        if not tag:
            return
        reply = QMessageBox.question(
            self, "Delete Tag",
            f"Delete tag '{tag['name']}'? It will be removed from all photos.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.db.delete_tag(tag_id)
            self._current_tag_id = None
            self.refresh()
