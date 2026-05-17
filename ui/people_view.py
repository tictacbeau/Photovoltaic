"""People view — face clusters, identity confirmation, adaptive recognition UI."""

import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QListWidget, QListWidgetItem, QScrollArea, QFrame, QGridLayout,
    QInputDialog, QMessageBox, QSplitter, QTextEdit, QMenu,
    QDialog, QDialogButtonBox, QComboBox, QProgressBar,
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal, QThread, QObject
from PyQt6.QtGui import QPixmap, QFont, QColor, QAction

from core.database import Database
from core.face_engine import FaceEngine, is_available
from utils.image_utils import pil_to_qpixmap, placeholder_pixmap, load_thumbnail


THUMB_SIZE = 96
FACE_THUMB_SIZE = 80


class FaceScanSignals(QObject):
    progress = pyqtSignal(int, int)
    finished = pyqtSignal(int)


class PeopleView(QWidget):
    """Main people/faces management screen."""

    def __init__(self, db: Database, face_engine: FaceEngine, parent=None):
        super().__init__(parent)
        self.db = db
        self.face_engine = face_engine
        self._scan_signals = FaceScanSignals()
        self._scan_signals.progress.connect(self._on_face_scan_progress)
        self._scan_signals.finished.connect(self._on_face_scan_finished)
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(24, 24, 24, 24)

        # Header
        header = QHBoxLayout()
        title = QLabel("People")
        title.setStyleSheet("font-size: 22px; font-weight: bold; color: #e0e0e0;")
        header.addWidget(title)
        header.addStretch()

        self.btn_scan_faces = QPushButton("⬤  Scan for Faces")
        self.btn_cluster = QPushButton("⧈  Auto-Group Faces")
        self.btn_add_person = QPushButton("+ New Person")
        for btn in [self.btn_scan_faces, self.btn_cluster, self.btn_add_person]:
            btn.setStyleSheet(_btn_style())
            btn.setFixedHeight(32)
        self.btn_scan_faces.setStyleSheet(_btn_style(primary=True))

        if not is_available():
            self.btn_scan_faces.setEnabled(False)
            self.btn_scan_faces.setToolTip(
                "face_recognition library not installed.\n"
                "Run: pip install cmake dlib face-recognition"
            )
            self.btn_cluster.setEnabled(False)

        header.addWidget(self.btn_scan_faces)
        header.addWidget(self.btn_cluster)
        header.addWidget(self.btn_add_person)
        layout.addLayout(header)

        if not is_available():
            banner = QLabel(
                "⚠  Facial recognition is not installed.  "
                "Install face-recognition to enable this feature:   "
                "pip install cmake dlib face-recognition"
            )
            banner.setStyleSheet(
                "background: #3a2a00; color: #f0c060; padding: 8px 14px; "
                "border-radius: 5px; font-size: 12px;"
            )
            layout.addWidget(banner)

        # Face scan progress bar (hidden until scan starts)
        self.face_progress = QProgressBar()
        self.face_progress.setTextVisible(True)
        self.face_progress.setStyleSheet(
            "QProgressBar { border: 1px solid #333; border-radius: 4px; background: #1a1a1a; "
            "color: #ccc; text-align: center; height: 16px; }"
            "QProgressBar::chunk { background: #6a4aaf; border-radius: 3px; }"
        )
        self.face_progress.setVisible(False)
        layout.addWidget(self.face_progress)

        # Main splitter: person list (left) | face grid (right)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter, 1)

        # ── Person list ───────────────────────────────────────────────────────
        left = QWidget()
        left.setMaximumWidth(280)
        left_layout = QVBoxLayout(left)
        left_layout.setSpacing(6)
        left_layout.setContentsMargins(0, 0, 8, 0)

        people_hdr = QHBoxLayout()
        pl = QLabel("People")
        pl.setStyleSheet("font-weight: bold; color: #aaa; font-size: 12px;")
        self.people_count_label = QLabel("")
        self.people_count_label.setStyleSheet("color: #555; font-size: 11px;")
        people_hdr.addWidget(pl)
        people_hdr.addStretch()
        people_hdr.addWidget(self.people_count_label)
        left_layout.addLayout(people_hdr)

        self.person_list = QListWidget()
        self.person_list.setStyleSheet(
            "QListWidget { background: #161616; border: 1px solid #2a2a2a; border-radius: 6px; color: #ddd; }"
            "QListWidget::item { padding: 8px 10px; border-bottom: 1px solid #1e1e1e; }"
            "QListWidget::item:selected { background: #1e3a5f; border-left: 3px solid #4a8abf; }"
            "QListWidget::item:hover { background: #1a1a1a; }"
        )
        self.person_list.currentRowChanged.connect(self._on_person_selected)
        self.person_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.person_list.customContextMenuRequested.connect(self._person_context_menu)
        left_layout.addWidget(self.person_list, 1)

        unassigned_btn = QPushButton("Unassigned Faces")
        unassigned_btn.setStyleSheet(_btn_style())
        unassigned_btn.setFixedHeight(30)
        unassigned_btn.clicked.connect(self._show_unassigned)
        left_layout.addWidget(unassigned_btn)

        splitter.addWidget(left)

        # ── Right: person detail + face grid ─────────────────────────────────
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setSpacing(8)
        right_layout.setContentsMargins(8, 0, 0, 0)

        # Person header card
        self.person_card = PersonCard()
        right_layout.addWidget(self.person_card)
        self.person_card.rename_requested.connect(self._rename_person)
        self.person_card.merge_requested.connect(self._merge_person)

        # Face tabs: Confirmed / Suggested / All
        tabs_row = QHBoxLayout()
        self.tab_buttons: dict[str, QPushButton] = {}
        for key, label in [("confirmed", "Confirmed"), ("suggested", "Suggested"), ("all", "All Faces")]:
            btn = QPushButton(label)
            btn.setStyleSheet(_tab_btn_style(active=key == "confirmed"))
            btn.setFixedHeight(28)
            btn.setCheckable(True)
            btn.setChecked(key == "confirmed")
            btn.clicked.connect(lambda checked, k=key: self._switch_tab(k))
            self.tab_buttons[key] = btn
            tabs_row.addWidget(btn)
        tabs_row.addStretch()
        right_layout.addLayout(tabs_row)

        self._active_tab = "confirmed"

        # Face grid
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: #111; }")
        self.face_grid_widget = QWidget()
        self.face_grid_widget.setStyleSheet("background: #111;")
        self.face_grid = QGridLayout(self.face_grid_widget)
        self.face_grid.setSpacing(8)
        self.face_grid.setContentsMargins(8, 8, 8, 8)
        scroll.setWidget(self.face_grid_widget)
        right_layout.addWidget(scroll, 1)

        splitter.addWidget(right)
        splitter.setSizes([260, 540])

        # Buttons
        self.btn_scan_faces.clicked.connect(self._start_face_scan)
        self.btn_cluster.clicked.connect(self._auto_cluster)
        self.btn_add_person.clicked.connect(self._add_person)

    # ── Data loading ──────────────────────────────────────────────────────────

    def refresh(self):
        self._load_person_list()

    def _load_person_list(self):
        self.person_list.clear()
        people = self.db.get_all_people()
        self.people_count_label.setText(f"{len(people)} people")
        for p in people:
            item = QListWidgetItem()
            label = p["name"]
            confirmed = p["confirmed_count"]
            threshold = p["match_threshold"]
            accuracy = int((1 - threshold) * 100)
            item.setText(f"{label}\n{confirmed} confirmed  ·  {accuracy}% accuracy")
            item.setData(Qt.ItemDataRole.UserRole, p["id"])
            # Color hint based on confirmed count
            if confirmed == 0:
                item.setForeground(QColor("#666"))
            elif confirmed < 5:
                item.setForeground(QColor("#c8a050"))
            else:
                item.setForeground(QColor("#78c890"))
            self.person_list.addItem(item)

    def _on_person_selected(self, row: int):
        if row < 0:
            return
        try:
            item = self.person_list.item(row)
            if not item:
                return
            person_id = item.data(Qt.ItemDataRole.UserRole)
            person = self.db.get_person(person_id)
            if not person:
                return
            self.person_card.set_person(person)
            self._load_face_grid(person_id)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).exception("Error loading person %s", row)

    def _load_face_grid(self, person_id: int):
        _clear_layout(self.face_grid)
        tab = self._active_tab
        if tab == "confirmed":
            faces = self.db.get_faces_for_person(person_id, confirmed_only=True)
        elif tab == "suggested":
            # Suggested = assigned but not confirmed
            conn = self.db._conn()
            faces = conn.execute(
                "SELECT f.*, p.file_path FROM faces f JOIN photos p ON f.photo_id=p.id "
                "WHERE f.person_id=? AND f.is_confirmed=0 AND f.is_ignored=0",
                (person_id,),
            ).fetchall()
        else:
            faces = self.db.get_faces_for_person(person_id, confirmed_only=False)

        cols = 5
        for idx, face in enumerate(faces):
            card = FaceCard(face, confirmed=(face["is_confirmed"] == 1))
            card.confirm_clicked.connect(lambda fid=face["id"], pid=person_id: self._confirm_face(fid, pid))
            card.reject_clicked.connect(lambda fid=face["id"], pid=person_id: self._reject_face(fid, pid))
            card.ignore_clicked.connect(lambda fid=face["id"]: self._ignore_face(fid))
            self.face_grid.addWidget(card, idx // cols, idx % cols)

        # Fill empty cells
        remainder = len(faces) % cols
        if remainder:
            for i in range(cols - remainder):
                self.face_grid.addWidget(QWidget(), (len(faces) // cols), remainder + i)

    def _show_unassigned(self):
        self.person_card.clear()
        _clear_layout(self.face_grid)
        faces = self.db.get_unassigned_faces()
        cols = 5
        for idx, face in enumerate(faces):
            card = FaceCard(face, confirmed=False, show_assign=True)
            card.assign_clicked.connect(lambda fid=face["id"]: self._assign_face(fid))
            card.ignore_clicked.connect(lambda fid=face["id"]: self._ignore_face(fid))
            self.face_grid.addWidget(card, idx // cols, idx % cols)

    def _switch_tab(self, key: str):
        self._active_tab = key
        for k, btn in self.tab_buttons.items():
            btn.setStyleSheet(_tab_btn_style(active=k == key))
            btn.setChecked(k == key)
        item = self.person_list.currentItem()
        if item:
            pid = item.data(Qt.ItemDataRole.UserRole)
            self._load_face_grid(pid)

    # ── Face actions ──────────────────────────────────────────────────────────

    def _confirm_face(self, face_id: int, person_id: int):
        self.db.confirm_face(face_id, person_id)
        self._load_person_list()
        self._load_face_grid(person_id)

    def _reject_face(self, face_id: int, person_id: int):
        self.db.reject_face(face_id, person_id)
        self._load_face_grid(person_id)

    def _ignore_face(self, face_id: int):
        self.db.ignore_face(face_id)
        item = self.person_list.currentItem()
        if item:
            self._load_face_grid(item.data(Qt.ItemDataRole.UserRole))
        else:
            self._show_unassigned()

    def _assign_face(self, face_id: int):
        people = self.db.get_all_people()
        if not people:
            QMessageBox.information(self, "No People", "Create a person first, then assign.")
            return
        names = [p["name"] for p in people]
        name, ok = QInputDialog.getItem(self, "Assign Face", "Choose person:", names, editable=False)
        if ok and name:
            pid = next(p["id"] for p in people if p["name"] == name)
            self.db.confirm_face(face_id, pid)
            self._show_unassigned()
            self._load_person_list()

    # ── Person actions ────────────────────────────────────────────────────────

    def _add_person(self):
        name, ok = QInputDialog.getText(self, "New Person", "Name:")
        if ok and name.strip():
            self.db.create_person(name.strip())
            self._load_person_list()

    def _rename_person(self, person_id: int, current_name: str):
        name, ok = QInputDialog.getText(self, "Rename Person", "New name:", text=current_name)
        if ok and name.strip():
            self.db.update_person(person_id, name=name.strip())
            self._load_person_list()

    def _merge_person(self, source_id: int):
        people = [p for p in self.db.get_all_people() if p["id"] != source_id]
        if not people:
            return
        names = [p["name"] for p in people]
        name, ok = QInputDialog.getItem(self, "Merge Into", "Merge into which person?", names, editable=False)
        if ok and name:
            target_id = next(p["id"] for p in people if p["name"] == name)
            reply = QMessageBox.question(
                self, "Confirm Merge",
                f"Merge all faces from this person into '{name}'?\nThis cannot be undone easily.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.db.merge_people(source_id, target_id)
                self._load_person_list()

    def _person_context_menu(self, pos):
        item = self.person_list.itemAt(pos)
        if not item:
            return
        pid = item.data(Qt.ItemDataRole.UserRole)
        person = self.db.get_person(pid)
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu { background: #1e1e1e; color: #ddd; border: 1px solid #333; }"
            "QMenu::item:selected { background: #2a4a6e; }"
        )
        rename_act = menu.addAction("Rename…")
        merge_act = menu.addAction("Merge into…")
        menu.addSeparator()
        hide_act = menu.addAction("Hide person")
        act = menu.exec(self.person_list.viewport().mapToGlobal(pos))
        if act == rename_act:
            self._rename_person(pid, person["name"])
        elif act == merge_act:
            self._merge_person(pid)
        elif act == hide_act:
            self.db.update_person(pid, is_hidden=1)
            self._load_person_list()

    # ── Face scanning ─────────────────────────────────────────────────────────

    def _start_face_scan(self):
        photos = self.db.get_all_photos()
        photo_ids = [p["id"] for p in photos]
        if not photo_ids:
            QMessageBox.information(self, "No Photos", "Run a file scan first to catalog photos.")
            return
        self.face_progress.setVisible(True)
        self.face_progress.setMaximum(len(photo_ids))
        self.face_progress.setValue(0)
        self.btn_scan_faces.setEnabled(False)
        self.face_engine.rebuild_person_models()
        self.face_engine.run_face_scan(
            photo_ids,
            on_progress=self._scan_signals.progress.emit,
            on_finished=self._scan_signals.finished.emit,
        )

    def _on_face_scan_progress(self, current: int, total: int):
        self.face_progress.setMaximum(total)
        self.face_progress.setValue(current)
        self.face_progress.setFormat(f"Scanning faces… {current}/{total}")

    def _on_face_scan_finished(self, face_count: int):
        self.face_progress.setVisible(False)
        self.btn_scan_faces.setEnabled(True)
        self._load_person_list()
        QMessageBox.information(self, "Face Scan Complete", f"Found {face_count} faces.")

    def _auto_cluster(self):
        reply = QMessageBox.question(
            self, "Auto-Group Faces",
            "Group all unassigned faces into people by similarity?\n"
            "You will still need to name and confirm each group.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        clusters = self.face_engine.cluster_unassigned_faces()
        if not clusters:
            QMessageBox.information(self, "Nothing to Group", "No unassigned faces found.")
            return
        for label, face_ids in clusters.items():
            if len(face_ids) >= 1:
                self.face_engine.auto_assign_cluster(face_ids)
        self._load_person_list()
        QMessageBox.information(
            self, "Grouped",
            f"Created {len(clusters)} person group(s) from unassigned faces.\n"
            "Please review and name each group.",
        )


# ── Sub-widgets ───────────────────────────────────────────────────────────────

class PersonCard(QFrame):
    rename_requested = pyqtSignal(int, str)
    merge_requested = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            "QFrame { background: #1a1a1a; border: 1px solid #2a2a2a; border-radius: 8px; }"
        )
        self.setFixedHeight(90)
        self._person_id: int | None = None
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(14)

        self._avatar = QLabel()
        self._avatar.setFixedSize(60, 60)
        self._avatar.setStyleSheet("border-radius: 30px; background: #2a2a2a;")
        self._avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._avatar)

        info = QVBoxLayout()
        info.setSpacing(2)
        self._name_label = QLabel("Select a person")
        self._name_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #e0e0e0;")
        self._stats_label = QLabel("")
        self._stats_label.setStyleSheet("font-size: 12px; color: #666;")
        self._accuracy_label = QLabel("")
        self._accuracy_label.setStyleSheet("font-size: 11px; color: #4a9a6a;")
        info.addWidget(self._name_label)
        info.addWidget(self._stats_label)
        info.addWidget(self._accuracy_label)
        layout.addLayout(info, 1)

        btn_col = QVBoxLayout()
        self._btn_rename = QPushButton("Rename")
        self._btn_merge = QPushButton("Merge")
        for btn in [self._btn_rename, self._btn_merge]:
            btn.setStyleSheet(_btn_style(small=True))
            btn.setFixedHeight(24)
            btn.setEnabled(False)
        self._btn_rename.clicked.connect(
            lambda: self.rename_requested.emit(self._person_id, self._name_label.text())
        )
        self._btn_merge.clicked.connect(lambda: self.merge_requested.emit(self._person_id))
        btn_col.addWidget(self._btn_rename)
        btn_col.addWidget(self._btn_merge)
        layout.addLayout(btn_col)

    def set_person(self, person):
        self._person_id = person["id"]
        self._name_label.setText(person["name"])
        confirmed = person["confirmed_count"]
        threshold = person["match_threshold"]
        accuracy_pct = int((1 - threshold) * 100)
        self._stats_label.setText(f"{confirmed} confirmed face{'s' if confirmed != 1 else ''}")
        self._accuracy_label.setText(f"Match accuracy: {accuracy_pct}%  (threshold {threshold:.2f})")
        self._btn_rename.setEnabled(True)
        self._btn_merge.setEnabled(True)
        thumb = person["representative_thumbnail"]
        if thumb and os.path.exists(thumb):
            px = QPixmap(thumb).scaled(
                60, 60, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._avatar.setPixmap(px)
        else:
            self._avatar.setText("👤")
            self._avatar.setStyleSheet("font-size: 28px; background: #2a2a2a; border-radius: 30px;")

    def clear(self):
        self._person_id = None
        self._name_label.setText("Unassigned Faces")
        self._stats_label.setText("")
        self._accuracy_label.setText("")
        self._avatar.setText("?")
        self._btn_rename.setEnabled(False)
        self._btn_merge.setEnabled(False)


class FaceCard(QFrame):
    confirm_clicked = pyqtSignal()
    reject_clicked = pyqtSignal()
    ignore_clicked = pyqtSignal()
    assign_clicked = pyqtSignal()

    def __init__(self, face_row, confirmed: bool = False, show_assign: bool = False, parent=None):
        super().__init__(parent)
        border_color = "#2a6a3a" if confirmed else "#2a2a2a"
        self.setStyleSheet(
            f"QFrame {{ background: #1a1a1a; border: 1px solid {border_color}; "
            f"border-radius: 8px; }}"
        )
        self.setFixedSize(FACE_THUMB_SIZE + 24, FACE_THUMB_SIZE + 52)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 6)
        layout.setSpacing(4)

        # Face thumbnail
        thumb_label = QLabel()
        thumb_label.setFixedSize(FACE_THUMB_SIZE, FACE_THUMB_SIZE)
        thumb_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        thumb_label.setStyleSheet("border-radius: 6px; background: #111;")
        thumb_path = face_row["thumbnail_path"]
        if thumb_path and os.path.exists(thumb_path):
            px = QPixmap(thumb_path).scaled(
                FACE_THUMB_SIZE, FACE_THUMB_SIZE,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            thumb_label.setPixmap(px)
        else:
            thumb_label.setText("👤")
            thumb_label.setStyleSheet("font-size: 32px; background: #222; border-radius: 6px;")
        layout.addWidget(thumb_label)

        # Confidence badge
        conf = face_row["confidence"] if face_row["confidence"] else 0.0
        conf_label = QLabel(f"{int(conf * 100)}%" if conf > 0 else "—")
        conf_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        conf_color = "#4a9a6a" if conf > 0.7 else "#c8a050" if conf > 0.4 else "#666"
        conf_label.setStyleSheet(f"font-size: 10px; color: {conf_color};")
        layout.addWidget(conf_label)

        # Action buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)
        if show_assign:
            btn_assign = QPushButton("Assign")
            btn_assign.setStyleSheet(_btn_style(primary=True, tiny=True))
            btn_assign.setFixedHeight(20)
            btn_assign.clicked.connect(self.assign_clicked)
            btn_row.addWidget(btn_assign)
        elif not confirmed:
            btn_ok = QPushButton("✓")
            btn_ok.setStyleSheet(_btn_style(primary=True, tiny=True))
            btn_ok.setFixedHeight(20)
            btn_ok.setToolTip("Confirm — this is the right person")
            btn_ok.clicked.connect(self.confirm_clicked)
            btn_no = QPushButton("✗")
            btn_no.setStyleSheet(_btn_style(danger=True, tiny=True))
            btn_no.setFixedHeight(20)
            btn_no.setToolTip("Reject — not this person")
            btn_no.clicked.connect(self.reject_clicked)
            btn_row.addWidget(btn_ok)
            btn_row.addWidget(btn_no)
        else:
            confirmed_lbl = QLabel("✓")
            confirmed_lbl.setStyleSheet("color: #4a9a6a; font-size: 13px;")
            confirmed_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            btn_row.addWidget(confirmed_lbl)

        btn_ign = QPushButton("–")
        btn_ign.setStyleSheet(_btn_style(tiny=True))
        btn_ign.setFixedHeight(20)
        btn_ign.setToolTip("Ignore this face")
        btn_ign.clicked.connect(self.ignore_clicked)
        btn_row.addWidget(btn_ign)
        layout.addLayout(btn_row)


# ── Utilities ─────────────────────────────────────────────────────────────────

def _clear_layout(layout):
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().deleteLater()


def _btn_style(primary=False, danger=False, small=False, tiny=False) -> str:
    pad = "2px 6px" if tiny else ("3px 8px" if small else "6px 12px")
    if primary:
        return (
            f"QPushButton {{ background: #2a6496; color: white; border: none; border-radius: 4px; padding: {pad}; font-weight: bold; }}"
            "QPushButton:hover { background: #3a74a6; }"
            "QPushButton:disabled { background: #333; color: #555; }"
        )
    if danger:
        return (
            f"QPushButton {{ background: #5a2020; color: #e08080; border: none; border-radius: 4px; padding: {pad}; }}"
            "QPushButton:hover { background: #7a3030; }"
        )
    return (
        f"QPushButton {{ background: #242424; color: #bbb; border: 1px solid #333; border-radius: 4px; padding: {pad}; }}"
        "QPushButton:hover { background: #2e2e2e; }"
        "QPushButton:disabled { color: #444; }"
    )


def _tab_btn_style(active: bool = False) -> str:
    if active:
        return (
            "QPushButton { background: #1e3a5f; color: #7ab8e0; border: 1px solid #2a5a8a; "
            "border-radius: 4px; padding: 4px 14px; font-weight: bold; }"
        )
    return (
        "QPushButton { background: #1a1a1a; color: #777; border: 1px solid #2a2a2a; "
        "border-radius: 4px; padding: 4px 14px; }"
        "QPushButton:hover { background: #222; color: #aaa; }"
    )
