"""Photo detail dialog — full image + metadata panel."""
import os
from PyQt6.QtWidgets import (QDialog, QHBoxLayout, QVBoxLayout, QLabel,
    QPushButton, QScrollArea, QWidget, QSizePolicy, QInputDialog, QMessageBox)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QPixmap, QKeyEvent
from ui.styles import btn_style
from core.database import Database


class PhotoDetailDialog(QDialog):
    def __init__(self, db: Database, photo_id: int, all_ids: list = None, parent=None):
        super().__init__(parent)
        self.db = db
        self._all_ids = all_ids or [photo_id]
        self._current_idx = self._all_ids.index(photo_id) if photo_id in self._all_ids else 0
        self._current_photo_id = photo_id
        self.setWindowTitle("Photo Detail")
        self.resize(1100, 720)
        self.setStyleSheet("QDialog { background: #111; } QLabel { color: #ccc; }")
        self._build_ui()
        self._load_photo(self._all_ids[self._current_idx])

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        # ── Image panel (left) ───────────────────────────────────────────────
        img_panel = QWidget()
        img_panel.setStyleSheet("background: #0a0a0a;")
        img_layout = QVBoxLayout(img_panel)
        img_layout.setContentsMargins(0, 0, 0, 0)

        self.img_label = QLabel()
        self.img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.img_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        img_layout.addWidget(self.img_label, 1)

        # Nav buttons
        nav_row = QHBoxLayout()
        nav_row.setContentsMargins(12, 8, 12, 8)
        self.btn_prev = QPushButton("◀  Previous")
        self.btn_next = QPushButton("Next  ▶")
        self.nav_label = QLabel()
        self.nav_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.nav_label.setStyleSheet("color: #555; font-size: 11px;")
        for btn in [self.btn_prev, self.btn_next]:
            btn.setStyleSheet(btn_style(small=True))
            btn.setFixedHeight(30)
        self.btn_prev.clicked.connect(self._prev)
        self.btn_next.clicked.connect(self._next)
        nav_row.addWidget(self.btn_prev)
        nav_row.addStretch()
        nav_row.addWidget(self.nav_label)
        nav_row.addStretch()
        nav_row.addWidget(self.btn_next)
        img_layout.addLayout(nav_row)
        layout.addWidget(img_panel, 1)

        # ── Metadata panel (right) ───────────────────────────────────────────
        meta_scroll = QScrollArea()
        meta_scroll.setWidgetResizable(True)
        meta_scroll.setFixedWidth(300)
        meta_scroll.setStyleSheet(
            "QScrollArea { background: #111; border: none; border-left: 1px solid #1e1e1e; }"
        )
        meta_widget = QWidget()
        meta_widget.setStyleSheet("background: #111;")
        self.meta_layout = QVBoxLayout(meta_widget)
        self.meta_layout.setContentsMargins(16, 16, 16, 16)
        self.meta_layout.setSpacing(12)
        meta_scroll.setWidget(meta_widget)
        layout.addWidget(meta_scroll)

    def _load_photo(self, photo_id: int):
        row = self.db.get_photo(photo_id)
        if not row:
            return
        self._current_photo_id = photo_id

        # Image
        path = row["file_path"]
        px = QPixmap(path) if os.path.exists(path) else None
        if px and not px.isNull():
            scaled = px.scaled(
                self.img_label.size().expandedTo(QSize(600, 500)),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.img_label.setPixmap(scaled)
        else:
            self.img_label.setText("⚠  File not found")
            self.img_label.setStyleSheet("color: #555; font-size: 14px;")

        # Nav state
        idx = self._all_ids.index(photo_id) if photo_id in self._all_ids else 0
        self.nav_label.setText(f"{idx + 1} / {len(self._all_ids)}")
        self.btn_prev.setEnabled(idx > 0)
        self.btn_next.setEnabled(idx < len(self._all_ids) - 1)

        # Metadata
        self._clear_meta()
        self._add_section("📄 File")
        self._add_row("Name", os.path.basename(path))
        if row["file_size"]:
            mb = row["file_size"] / (1024 * 1024)
            self._add_row("Size", f"{mb:.1f} MB" if mb >= 1 else f"{row['file_size']:,} B")
        if row["width"] and row["height"]:
            self._add_row("Resolution", f"{row['width']} × {row['height']}")
        self._add_row("Type", row["file_type"] or os.path.splitext(path)[1].upper())
        self._add_row("Path", row["file_path"], wrap=True)

        if row["exif_date"] or row["camera_make"] or row["camera_model"]:
            self._add_section("📷 Camera")
            if row["exif_date"]:
                self._add_row("Date taken", row["exif_date"][:19])
            if row["camera_make"]:
                self._add_row("Make", row["camera_make"])
            if row["camera_model"]:
                self._add_row("Model", row["camera_model"])

        if row["gps_lat"] and row["gps_lon"]:
            self._add_section("📍 Location")
            self._add_row("GPS", f"{row['gps_lat']:.5f}, {row['gps_lon']:.5f}")

        # Faces
        faces = self.db.get_faces_for_photo(photo_id)
        if faces:
            self._add_section(f"👤 Faces ({len(faces)})")
            for face in faces:
                pid = face["person_id"]
                if pid:
                    p = self.db.get_person(pid)
                    name = p["name"] if p else "Unknown"
                    tag = "✓" if face["is_confirmed"] else "?"
                    self._add_row(tag, name)
                else:
                    self._add_row("·", "Unassigned")

        # Albums
        albums = self.db.get_albums_for_photo(photo_id)
        self._add_section("🗂 Albums")
        if albums:
            for a in albums:
                row_w = QWidget()
                rlay = QHBoxLayout(row_w)
                rlay.setContentsMargins(0, 0, 0, 0)
                lbl = QLabel(a["name"])
                lbl.setStyleSheet("color: #9ab; font-size: 11px;")
                rlay.addWidget(lbl, 1)
                rem_btn = QPushButton("✕")
                rem_btn.setStyleSheet(btn_style(tiny=True, danger=True))
                rem_btn.setFixedSize(20, 20)
                rem_btn.setToolTip("Remove from album")
                album_id = a["id"]
                rem_btn.clicked.connect(lambda checked, aid=album_id: self._remove_from_album(aid))
                rlay.addWidget(rem_btn)
                self.meta_layout.addWidget(row_w)
        else:
            empty = QLabel("Not in any album")
            empty.setStyleSheet("color: #444; font-size: 11px;")
            self.meta_layout.addWidget(empty)

        add_btn = QPushButton("+ Add to Album")
        add_btn.setStyleSheet(btn_style(small=True))
        add_btn.setFixedHeight(28)
        add_btn.clicked.connect(self._add_to_album)
        self.meta_layout.addWidget(add_btn)

        # Tags
        tags = self.db.get_tags_for_photo(photo_id)
        self._add_section("🏷 Tags")
        if tags:
            for tag in tags:
                tag_w = QWidget()
                tlay = QHBoxLayout(tag_w)
                tlay.setContentsMargins(0, 0, 0, 0)
                lbl = QLabel(tag["name"])
                lbl.setStyleSheet("color: #9ba; font-size: 11px;")
                tlay.addWidget(lbl, 1)
                rem_btn = QPushButton("✕")
                rem_btn.setStyleSheet(btn_style(tiny=True, danger=True))
                rem_btn.setFixedSize(20, 20)
                tag_name = tag["name"]
                rem_btn.clicked.connect(lambda checked, tn=tag_name: self._remove_tag(tn))
                tlay.addWidget(rem_btn)
                self.meta_layout.addWidget(tag_w)
        else:
            no_tags = QLabel("No tags")
            no_tags.setStyleSheet("color: #444; font-size: 11px;")
            self.meta_layout.addWidget(no_tags)

        add_tag_btn = QPushButton("+ Add Tag")
        add_tag_btn.setStyleSheet(btn_style(small=True))
        add_tag_btn.setFixedHeight(28)
        add_tag_btn.clicked.connect(self._add_tag)
        self.meta_layout.addWidget(add_tag_btn)
        self.meta_layout.addStretch()

    def _remove_from_album(self, album_id: int):
        self.db.remove_photo_from_album(album_id, self._current_photo_id)
        self._load_photo(self._current_photo_id)

    def _add_to_album(self):
        albums = self.db.get_all_albums()
        if not albums:
            QMessageBox.information(self, "No Albums", "Create an album first in the Albums view.")
            return
        names = [f"{a['name']}  ({a['photo_count']} photos)" for a in albums]
        item, ok = QInputDialog.getItem(self, "Add to Album", "Select album:", names, 0, False)
        if ok and item:
            idx = names.index(item)
            self.db.add_photo_to_album(albums[idx]["id"], self._current_photo_id)
            self._load_photo(self._current_photo_id)

    def _add_tag(self):
        tag_name, ok = QInputDialog.getText(self, "Add Tag", "Tag name:")
        if ok and tag_name.strip():
            self.db.add_tag_to_photo(self._current_photo_id, tag_name.strip())
            self._load_photo(self._current_photo_id)

    def _remove_tag(self, tag_name: str):
        self.db.remove_tag_from_photo(self._current_photo_id, tag_name)
        self._load_photo(self._current_photo_id)

    def _clear_meta(self):
        while self.meta_layout.count():
            child = self.meta_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    def _add_section(self, title: str):
        lbl = QLabel(title)
        lbl.setStyleSheet(
            "font-size: 11px; font-weight: bold; color: #7ab8e0; "
            "border-top: 1px solid #222; padding-top: 8px; margin-top: 4px;"
        )
        self.meta_layout.addWidget(lbl)

    def _add_row(self, key: str, value: str, wrap: bool = False):
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        k = QLabel(key + ":")
        k.setStyleSheet("color: #555; font-size: 11px; min-width: 60px;")
        k.setFixedWidth(72)
        v = QLabel(str(value))
        v.setStyleSheet("color: #aaa; font-size: 11px;")
        if wrap:
            v.setWordWrap(True)
        lay.addWidget(k)
        lay.addWidget(v, 1)
        self.meta_layout.addWidget(w)

    def _prev(self):
        idx = self._all_ids.index(self._current_photo_id)
        if idx > 0:
            self._current_idx = idx - 1
            self._load_photo(self._all_ids[self._current_idx])

    def _next(self):
        idx = self._all_ids.index(self._current_photo_id)
        if idx < len(self._all_ids) - 1:
            self._current_idx = idx + 1
            self._load_photo(self._all_ids[self._current_idx])

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Left:
            self._prev()
        elif event.key() == Qt.Key.Key_Right:
            self._next()
        elif event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, '_current_photo_id') and hasattr(self, 'img_label'):
            row = self.db.get_photo(self._current_photo_id)
            if row:
                path = row["file_path"]
                if os.path.exists(path):
                    px = QPixmap(path)
                    if not px.isNull():
                        scaled = px.scaled(
                            self.img_label.size(),
                            Qt.AspectRatioMode.KeepAspectRatio,
                            Qt.TransformationMode.SmoothTransformation,
                        )
                        self.img_label.setPixmap(scaled)
