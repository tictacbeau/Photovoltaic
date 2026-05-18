"""Duplicate Manager — review and resolve duplicate photo groups."""
import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QScrollArea, QFrame,
    QMessageBox, QSizePolicy, QSplitter,
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QPixmap, QColor

from ui.styles import btn_style
from core.database import Database

CARD_W = 200
THUMB_H = 160


class DuplicateView(QWidget):
    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        self._groups = []
        self._current_group_id = None
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

        title = QLabel("Duplicates")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #c0d0e0; min-width: 100px;")
        tbar.addWidget(title)

        self.count_label = QLabel("No duplicate groups")
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

        # Left — group list
        left = QWidget()
        left.setFixedWidth(220)
        left.setStyleSheet("background: #111;")
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.setSpacing(0)

        lbl = QLabel("  Groups")
        lbl.setStyleSheet(
            "color: #555; font-size: 11px; padding: 8px 12px; "
            "border-bottom: 1px solid #1a1a1a; background: #0d0d0d;"
        )
        lbl.setFixedHeight(30)
        left_lay.addWidget(lbl)

        self.group_list = QListWidget()
        self.group_list.setStyleSheet(
            "QListWidget { background: #111; border: none; outline: none; }"
            "QListWidget::item { color: #888; font-size: 12px; padding: 10px 14px; "
            "  border-bottom: 1px solid #1a1a1a; }"
            "QListWidget::item:selected { background: #152535; color: #b0d0f0; }"
            "QListWidget::item:hover { background: #161616; }"
        )
        self.group_list.currentRowChanged.connect(self._on_group_selected)
        left_lay.addWidget(self.group_list, 1)
        splitter.addWidget(left)

        # Right — photo cards
        right = QWidget()
        right.setStyleSheet("background: #141414;")
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(0, 0, 0, 0)
        right_lay.setSpacing(0)

        # Group action bar (shown when a group is selected)
        self.action_bar = QWidget()
        self.action_bar.setStyleSheet("background: #0d0d0d; border-bottom: 1px solid #1e1e1e;")
        self.action_bar.setFixedHeight(46)
        abar = QHBoxLayout(self.action_bar)
        abar.setContentsMargins(16, 6, 16, 6)
        abar.setSpacing(10)

        self.group_info_lbl = QLabel()
        self.group_info_lbl.setStyleSheet("color: #666; font-size: 11px;")
        abar.addWidget(self.group_info_lbl)
        abar.addStretch()

        keep_best_btn = QPushButton("⭐ Keep Best")
        keep_best_btn.setToolTip("Keep highest-resolution photo, delete the rest")
        keep_best_btn.setStyleSheet(btn_style(small=True))
        keep_best_btn.setFixedHeight(30)
        keep_best_btn.clicked.connect(self._keep_best)

        keep_all_btn = QPushButton("✓ Keep All")
        keep_all_btn.setToolTip("Dismiss this group without deleting anything")
        keep_all_btn.setStyleSheet(btn_style(small=True))
        keep_all_btn.setFixedHeight(30)
        keep_all_btn.clicked.connect(self._keep_all)

        skip_btn = QPushButton("Skip →")
        skip_btn.setStyleSheet(btn_style(small=True))
        skip_btn.setFixedHeight(30)
        skip_btn.clicked.connect(self._skip)

        for b in [keep_best_btn, keep_all_btn, skip_btn]:
            abar.addWidget(b)

        self.action_bar.hide()
        right_lay.addWidget(self.action_bar)

        # Scroll area for cards
        self.card_scroll = QScrollArea()
        self.card_scroll.setWidgetResizable(True)
        self.card_scroll.setStyleSheet(
            "QScrollArea { background: #141414; border: none; }"
        )
        self.card_container = QWidget()
        self.card_container.setStyleSheet("background: #141414;")
        self.card_layout = QHBoxLayout(self.card_container)
        self.card_layout.setContentsMargins(20, 20, 20, 20)
        self.card_layout.setSpacing(16)
        self.card_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.card_scroll.setWidget(self.card_container)

        self.empty_label = QLabel("Select a duplicate group from the left panel")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet("color: #333; font-size: 14px;")

        right_lay.addWidget(self.card_scroll, 1)
        splitter.addWidget(right)

        root.addWidget(splitter, 1)

    # ── Public ───────────────────────────────────────────────────────────────

    def refresh(self):
        self._groups = self.db.get_duplicate_groups()
        n = len(self._groups)
        self.count_label.setText(
            f"{n} duplicate group{'s' if n != 1 else ''}" if n else "No duplicate groups"
        )
        self.group_list.blockSignals(True)
        self.group_list.clear()
        for g in self._groups:
            item = QListWidgetItem(
                f"Group #{g['id']}\n{g['member_count']} photos"
            )
            item.setData(Qt.ItemDataRole.UserRole, g["id"])
            self.group_list.addItem(item)
        self.group_list.blockSignals(False)
        if self._groups:
            self.group_list.setCurrentRow(0)
        else:
            self._clear_cards()
            self.action_bar.hide()

    # ── Internal ─────────────────────────────────────────────────────────────

    def _on_group_selected(self, row: int):
        if row < 0 or row >= len(self._groups):
            return
        self._current_group_id = self._groups[row]["id"]
        self._load_group(self._current_group_id)

    def _load_group(self, group_id: int):
        photos = self.db.get_duplicate_group_photos(group_id)
        self._clear_cards()
        if not photos:
            return
        self.action_bar.show()
        total_size = sum((p["file_size"] or 0) for p in photos)
        self.group_info_lbl.setText(
            f"{len(photos)} duplicates  ·  "
            f"{total_size / (1024*1024):.1f} MB total  ·  "
            f"Keep one to reclaim space"
        )
        for photo in photos:
            card = self._make_card(group_id, photo)
            self.card_layout.addWidget(card)
        self.card_layout.addStretch()

    def _make_card(self, group_id: int, photo: dict) -> QWidget:
        card = QFrame()
        card.setFixedWidth(CARD_W)
        is_master = bool(photo["is_master"])
        card.setStyleSheet(
            f"QFrame {{ background: {'#152535' if is_master else '#1a1a1a'}; "
            f"border: 1px solid {'#4a8abf' if is_master else '#222'}; border-radius: 6px; }}"
        )
        lay = QVBoxLayout(card)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        # Thumbnail
        thumb_lbl = QLabel()
        thumb_lbl.setFixedSize(CARD_W - 16, THUMB_H)
        thumb_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        thumb_lbl.setStyleSheet("background: #111; border-radius: 4px;")
        path = photo["thumbnail_path"] or photo["file_path"]
        px = QPixmap(str(path)) if path and os.path.exists(str(path)) else None
        if px and not px.isNull():
            thumb_lbl.setPixmap(
                px.scaled(CARD_W - 16, THUMB_H,
                          Qt.AspectRatioMode.KeepAspectRatio,
                          Qt.TransformationMode.SmoothTransformation)
            )
        else:
            thumb_lbl.setText("⚠ No image")
            thumb_lbl.setStyleSheet("color: #444; font-size: 11px; background: #111; border-radius: 4px;")
        lay.addWidget(thumb_lbl)

        # File name
        name_lbl = QLabel(os.path.basename(photo["file_path"]))
        name_lbl.setStyleSheet("color: #aaa; font-size: 10px;")
        name_lbl.setWordWrap(True)
        lay.addWidget(name_lbl)

        # Metadata
        meta_parts = []
        if photo["file_size"]:
            mb = photo["file_size"] / (1024 * 1024)
            meta_parts.append(f"{mb:.1f} MB" if mb >= 1 else f"{photo['file_size']:,} B")
        if photo["width"] and photo["height"]:
            meta_parts.append(f"{photo['width']}×{photo['height']}")
        if is_master:
            meta_parts.append("★ master")
        meta_lbl = QLabel("  ·  ".join(meta_parts))
        meta_lbl.setStyleSheet("color: #5a8; font-size: 10px;" if is_master else "color: #555; font-size: 10px;")
        meta_lbl.setWordWrap(True)
        lay.addWidget(meta_lbl)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        keep_btn = QPushButton("Keep")
        keep_btn.setStyleSheet(btn_style(small=True))
        keep_btn.setFixedHeight(26)
        keep_btn.setToolTip("Keep this photo, delete all others in group")
        photo_id = photo["id"]
        keep_btn.clicked.connect(lambda: self._keep_one(group_id, photo_id))

        del_btn = QPushButton("Delete")
        del_btn.setStyleSheet(btn_style(small=True, danger=True))
        del_btn.setFixedHeight(26)
        del_btn.setToolTip("Delete this photo from disk and database")
        del_btn.clicked.connect(lambda: self._delete_one(group_id, photo_id))

        btn_row.addWidget(keep_btn)
        btn_row.addWidget(del_btn)
        lay.addLayout(btn_row)

        return card

    def _clear_cards(self):
        while self.card_layout.count():
            child = self.card_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def _keep_one(self, group_id: int, photo_id: int):
        photos = self.db.get_duplicate_group_photos(group_id)
        others = [p["id"] for p in photos if p["id"] != photo_id]
        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Keep this photo and delete {len(others)} other(s) from disk?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.db.set_duplicate_master(group_id, photo_id)
        for oid in others:
            self.db.delete_photo(oid, delete_file=True)
        self.db.dismiss_duplicate_group(group_id)
        self._advance_after_action()

    def _delete_one(self, group_id: int, photo_id: int):
        reply = QMessageBox.question(
            self, "Confirm Delete",
            "Delete this photo from disk and database?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.db.delete_photo(photo_id, delete_file=True)
        # If only 1 photo remains in group, dismiss it
        remaining = self.db.get_duplicate_group_photos(group_id)
        if len(remaining) <= 1:
            self.db.dismiss_duplicate_group(group_id)
            self._advance_after_action()
        else:
            self._load_group(group_id)

    def _keep_best(self):
        if self._current_group_id is None:
            return
        photos = self.db.get_duplicate_group_photos(self._current_group_id)
        if not photos:
            return
        # Best = largest pixel count, tie-break by file_size
        def score(p):
            return ((p["width"] or 0) * (p["height"] or 0), p["file_size"] or 0)
        best = max(photos, key=score)
        self._keep_one(self._current_group_id, best["id"])

    def _keep_all(self):
        if self._current_group_id is None:
            return
        self.db.dismiss_duplicate_group(self._current_group_id)
        self._advance_after_action()

    def _skip(self):
        self._advance_after_action()

    def _advance_after_action(self):
        """Reload groups and move to next (or stay at same index)."""
        current_row = self.group_list.currentRow()
        self.refresh()
        new_count = self.group_list.count()
        if new_count > 0:
            next_row = min(current_row, new_count - 1)
            self.group_list.setCurrentRow(next_row)
