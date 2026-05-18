"""Main application window with sidebar navigation."""

import os
import json
import logging
from pathlib import Path

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QPushButton, QLabel, QStackedWidget, QFrame,
    QMessageBox, QFileDialog, QStatusBar, QSizePolicy,
)
from PyQt6.QtCore import Qt, QSize, QTimer
from PyQt6.QtGui import QIcon, QFont, QColor

from core.database import Database
from core.face_engine import FaceEngine
from ui.styles import btn_style
from ui.scan_view import ScanView
from ui.people_view import PeopleView
from ui.gallery_view import GalleryView
from ui.album_view import AlbumView
from ui.duplicate_view import DuplicateView
from ui.timeline_view import TimelineView
from ui.smart_album_view import SmartAlbumView

log = logging.getLogger(__name__)

DEFAULT_APP_DIR = os.path.join(Path.home(), ".photovault")


class MainWindow(QMainWindow):
    def __init__(self, app_dir: str = DEFAULT_APP_DIR):
        super().__init__()
        self.app_dir = app_dir
        self.config = _load_config(app_dir)
        self.db = _init_db(self.config, app_dir)
        self.thumb_dir = self.config.get("thumb_dir", os.path.join(app_dir, "thumbnails"))
        os.makedirs(self.thumb_dir, exist_ok=True)
        self.face_engine = FaceEngine(self.db, self.thumb_dir)
        self._setup_window()
        self._build_ui()
        self._apply_style()
        self._refresh_status()

        # Restore saved scan folders
        saved_folders = self.config.get("scan_folders", [])
        if saved_folders:
            self.scan_view.set_folders(saved_folders)

        # Status bar refresh timer
        timer = QTimer(self)
        timer.timeout.connect(self._refresh_status)
        timer.start(10_000)

    # ── Setup ─────────────────────────────────────────────────────────────────

    def _setup_window(self):
        self.setWindowTitle("PhotoVault")
        self.setMinimumSize(960, 640)
        self.resize(1280, 800)

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setSpacing(0)
        root.setContentsMargins(0, 0, 0, 0)

        # ── Sidebar ───────────────────────────────────────────────────────────
        self.sidebar = _Sidebar()
        root.addWidget(self.sidebar)

        # ── Content stack ─────────────────────────────────────────────────────
        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)

        # Pages
        self.gallery_view = GalleryView(self.db)
        self.album_view = AlbumView(self.db)
        self.people_view = PeopleView(self.db, self.face_engine)
        self.scan_view = ScanView(self.db, self.thumb_dir)
        self.duplicate_view = DuplicateView(self.db)
        self.timeline_view = TimelineView(self.db)
        self.smart_album_view = SmartAlbumView(self.db)

        self.stack.addWidget(self.gallery_view)      # index 0
        self.stack.addWidget(self.album_view)        # index 1
        self.stack.addWidget(self.people_view)       # index 2
        self.stack.addWidget(self.scan_view)         # index 3
        self.stack.addWidget(self.duplicate_view)    # index 4
        self.stack.addWidget(self.timeline_view)     # index 5
        self.stack.addWidget(self.smart_album_view)  # index 6

        # Wire sidebar
        self.sidebar.nav_clicked.connect(self._navigate)
        self.sidebar.select(0)
        self.gallery_view.refresh()

        # Wire scan completion → refresh people
        self.scan_view.scan_complete.connect(self._on_scan_complete)

        # Export button in status bar
        self._export_btn = QPushButton("⬆ Export…")
        self._export_btn.setStyleSheet(btn_style(small=True))
        self._export_btn.setFixedHeight(24)
        self._export_btn.clicked.connect(self._open_export)

        # Status bar
        self.status = QStatusBar()
        self.status.setStyleSheet("QStatusBar { background: #111; color: #555; font-size: 11px; }")
        self.status.addPermanentWidget(self._export_btn)
        self.setStatusBar(self.status)

    # ── Navigation ────────────────────────────────────────────────────────────

    def _navigate(self, index: int):
        self.stack.setCurrentIndex(index)
        if index == 0:
            self.gallery_view.refresh()
        elif index == 1:
            self.album_view.refresh()
        elif index == 2:
            self.people_view.refresh()
        elif index == 4:
            self.duplicate_view.refresh()
        elif index == 5:
            self.timeline_view.refresh()
        elif index == 6:
            self.smart_album_view.refresh()

    def _open_export(self):
        from ui.export_dialog import ExportDialog
        dlg = ExportDialog(self.db, parent=self)
        dlg.exec()

    # ── Events ────────────────────────────────────────────────────────────────

    def _on_scan_complete(self, stats: dict):
        self._save_scan_folders()
        self._refresh_status()
        # Offer to run face scan
        from core.face_engine import is_available
        if is_available() and stats.get("new_photos", 0) > 0:
            reply = QMessageBox.question(
                self,
                "Scan Faces?",
                f"{stats['new_photos']:,} new photos were added.\n"
                "Would you like to scan them for faces now?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.sidebar.select(2)
                self._navigate(2)
                self.people_view._start_face_scan()
        else:
            # Navigate to gallery to show newly scanned photos
            self.sidebar.select(0)
            self._navigate(0)

    def _save_scan_folders(self):
        self.config["scan_folders"] = self.scan_view.get_folders()
        _save_config(self.config, self.app_dir)

    def _refresh_status(self):
        stats = self.db.get_stats()
        self.status.showMessage(
            f"  {stats['total_photos']:,} photos  ·  "
            f"{stats['total_people']} people  ·  "
            f"{stats['confirmed_faces']:,} confirmed faces  ·  "
            f"{stats['unassigned_faces']:,} unassigned faces  ·  "
            f"{stats['duplicate_groups']:,} duplicate groups"
        )

    def _apply_style(self):
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background: #141414;
                color: #ddd;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 13px;
            }
            QScrollBar:vertical {
                background: #1a1a1a; width: 8px; border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: #333; border-radius: 4px; min-height: 20px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
            QScrollBar:horizontal {
                background: #1a1a1a; height: 8px; border-radius: 4px;
            }
            QScrollBar::handle:horizontal {
                background: #333; border-radius: 4px; min-width: 20px;
            }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
            QToolTip {
                background: #222; color: #ccc; border: 1px solid #444;
                padding: 4px 8px; border-radius: 4px;
            }
        """)

    def closeEvent(self, event):
        self._save_scan_folders()
        super().closeEvent(event)


# ── Sidebar ───────────────────────────────────────────────────────────────────

from PyQt6.QtCore import pyqtSignal as Signal


class _Sidebar(QFrame):
    nav_clicked = Signal(int)

    NAV_ITEMS = [
        ("🖼 Gallery", "Gallery\nBrowse all photos", 0),
        ("🗂 Albums", "Albums\nOrganize into collections", 1),
        ("◉ People", "People\nFaces & recognition", 2),
        ("⬤ Scan", "Scanner\nFind & catalog photos", 3),
        ("⧉ Dupes", "Duplicates\nReview duplicate photos", 4),
        ("📅 Timeline", "Timeline\nBrowse by date", 5),
        ("✦ Smart", "Smart Albums\nAuto-generated collections", 6),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(200)
        self.setStyleSheet(
            "QFrame { background: #0e0e0e; border-right: 1px solid #1e1e1e; }"
        )
        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        # Logo / app name
        logo_frame = QFrame()
        logo_frame.setStyleSheet("background: #0a0a0a; border-bottom: 1px solid #1a1a1a;")
        logo_frame.setFixedHeight(64)
        logo_layout = QVBoxLayout(logo_frame)
        logo_layout.setContentsMargins(16, 0, 16, 0)
        logo_label = QLabel("PhotoVault")
        logo_label.setStyleSheet("font-size: 17px; font-weight: bold; color: #7ab8e0; letter-spacing: 1px;")
        tag_label = QLabel("Local Photo Manager")
        tag_label.setStyleSheet("font-size: 10px; color: #444;")
        logo_layout.addWidget(logo_label)
        logo_layout.addWidget(tag_label)
        layout.addWidget(logo_frame)

        # Nav buttons
        self._buttons: list[QPushButton] = []
        nav_container = QWidget()
        nav_layout = QVBoxLayout(nav_container)
        nav_layout.setSpacing(2)
        nav_layout.setContentsMargins(8, 12, 8, 12)
        for label, tooltip, idx in self.NAV_ITEMS:
            parts = label.split(" ", 1)
            icon_char = parts[0]
            text = parts[1] if len(parts) > 1 else ""
            btn = _NavButton(icon_char, text, tooltip, idx)
            btn.clicked.connect(lambda checked, i=idx: self.nav_clicked.emit(i))
            self._buttons.append(btn)
            nav_layout.addWidget(btn)
        nav_layout.addStretch()
        layout.addWidget(nav_container, 1)

        # Privacy notice at bottom
        privacy = QLabel("All data stays local.\nNo cloud, no uploads.")
        privacy.setStyleSheet("color: #2a4a2a; font-size: 10px; padding: 8px 14px;")
        privacy.setWordWrap(True)
        layout.addWidget(privacy)

    def select(self, index: int):
        for btn in self._buttons:
            btn.set_active(btn.nav_index == index)


class _NavButton(QFrame):
    clicked = Signal()

    def __init__(self, icon: str, label: str, tooltip: str, nav_index: int, parent=None):
        super().__init__(parent)
        self.nav_index = nav_index
        self.setFixedHeight(52)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(tooltip)
        self._active = False
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(10)
        self._icon_lbl = QLabel(icon)
        self._icon_lbl.setStyleSheet("font-size: 16px; color: #555;")
        self._icon_lbl.setFixedWidth(20)
        self._text_lbl = QLabel(label)
        self._text_lbl.setStyleSheet("font-size: 13px; color: #666;")
        layout.addWidget(self._icon_lbl)
        layout.addWidget(self._text_lbl, 1)
        self._update_style()

    def set_active(self, active: bool):
        self._active = active
        self._update_style()

    def _update_style(self):
        if self._active:
            self.setStyleSheet(
                "QFrame { background: #152535; border-left: 3px solid #4a8abf; border-radius: 6px; }"
            )
            self._icon_lbl.setStyleSheet("font-size: 16px; color: #7ab8e0;")
            self._text_lbl.setStyleSheet("font-size: 13px; color: #c0d8f0; font-weight: bold;")
        else:
            self.setStyleSheet(
                "QFrame { background: transparent; border-left: 3px solid transparent; border-radius: 6px; }"
                "QFrame:hover { background: #161616; }"
            )
            self._icon_lbl.setStyleSheet("font-size: 16px; color: #555;")
            self._text_lbl.setStyleSheet("font-size: 13px; color: #666;")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


# ── Config helpers ────────────────────────────────────────────────────────────

def _load_config(app_dir: str) -> dict:
    os.makedirs(app_dir, exist_ok=True)
    config_path = os.path.join(app_dir, "config.json")
    if os.path.exists(config_path):
        try:
            with open(config_path) as f:
                return json.load(f)
        except Exception:
            pass
    # Copy default config
    default_path = os.path.join(os.path.dirname(__file__), "..", "config", "default_config.json")
    if os.path.exists(default_path):
        with open(default_path) as f:
            cfg = json.load(f)
    else:
        cfg = {}
    cfg["app_dir"] = app_dir
    cfg["db_path"] = os.path.join(app_dir, "photovault.db")
    cfg["thumb_dir"] = os.path.join(app_dir, "thumbnails")
    _save_config(cfg, app_dir)
    return cfg


def _save_config(config: dict, app_dir: str):
    os.makedirs(app_dir, exist_ok=True)
    with open(os.path.join(app_dir, "config.json"), "w") as f:
        json.dump(config, f, indent=2)


def _init_db(config: dict, app_dir: str) -> Database:
    db_path = config.get("db_path", os.path.join(app_dir, "photovault.db"))
    return Database(db_path)
