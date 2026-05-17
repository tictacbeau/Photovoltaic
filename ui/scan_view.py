"""Scanner UI — folder selection, scan progress, and results summary."""

import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QListWidget, QListWidgetItem, QProgressBar, QFileDialog,
    QFrame, QGroupBox, QSplitter, QTextEdit, QCheckBox, QSpinBox,
    QScrollArea,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QObject
from ui.styles import btn_style as _btn_style
from PyQt6.QtGui import QFont, QColor

from core.database import Database
from core.scanner import ScanWorker


class ScanSignals(QObject):
    progress = pyqtSignal(int, int, str)
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)


class ScanView(QWidget):
    scan_complete = pyqtSignal(dict)

    def __init__(self, db: Database, thumb_dir: str, parent=None):
        super().__init__(parent)
        self.db = db
        self.thumb_dir = thumb_dir
        self._worker: ScanWorker | None = None
        self._signals = ScanSignals()
        self._signals.progress.connect(self._on_progress)
        self._signals.finished.connect(self._on_finished)
        self._signals.error.connect(self._on_error)
        self._build_ui()
        self._refresh_folder_list()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        # Title
        title = QLabel("Photo Scanner")
        title.setStyleSheet("font-size: 22px; font-weight: bold; color: #e0e0e0;")
        layout.addWidget(title)

        subtitle = QLabel("Scan your computer for photos and build the master catalog.")
        subtitle.setStyleSheet("color: #888; font-size: 13px;")
        layout.addWidget(subtitle)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter, 1)

        # ── Left panel: folder management ────────────────────────────────────
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setSpacing(10)
        left_layout.setContentsMargins(0, 0, 8, 0)

        folders_label = QLabel("Scan Folders")
        folders_label.setStyleSheet("font-weight: bold; color: #ccc; font-size: 13px;")
        left_layout.addWidget(folders_label)

        self.folder_list = QListWidget()
        self.folder_list.setStyleSheet(
            "QListWidget { background: #1e1e1e; border: 1px solid #333; border-radius: 6px; color: #ddd; }"
            "QListWidget::item { padding: 6px 8px; }"
            "QListWidget::item:selected { background: #2a4a6e; }"
        )
        self.folder_list.setMinimumHeight(200)
        left_layout.addWidget(self.folder_list)

        btn_row = QHBoxLayout()
        self.btn_add_folder = QPushButton("+ Add Folder")
        self.btn_remove_folder = QPushButton("Remove")
        for btn in [self.btn_add_folder, self.btn_remove_folder]:
            btn.setStyleSheet(_btn_style())
            btn.setFixedHeight(32)
        self.btn_remove_folder.setStyleSheet(_btn_style(danger=True))
        btn_row.addWidget(self.btn_add_folder)
        btn_row.addWidget(self.btn_remove_folder)
        btn_row.addStretch()
        left_layout.addLayout(btn_row)

        self.btn_add_folder.clicked.connect(self._add_folder)
        self.btn_remove_folder.clicked.connect(self._remove_folder)

        # Quick-add common locations
        quick_label = QLabel("Quick add:")
        quick_label.setStyleSheet("color: #666; font-size: 11px; margin-top: 8px;")
        left_layout.addWidget(quick_label)

        quick_row = QHBoxLayout()
        for label, path in _common_photo_dirs():
            if os.path.exists(path):
                btn = QPushButton(label)
                btn.setStyleSheet(_btn_style(small=True))
                btn.setFixedHeight(26)
                btn.clicked.connect(lambda checked, p=path: self._add_folder_path(p))
                quick_row.addWidget(btn)
        quick_row.addStretch()
        left_layout.addLayout(quick_row)

        # Options
        opts_box = QGroupBox("Options")
        opts_box.setStyleSheet(
            "QGroupBox { color: #aaa; border: 1px solid #333; border-radius: 6px; margin-top: 8px; padding-top: 8px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 10px; color: #aaa; }"
        )
        opts_layout = QVBoxLayout(opts_box)
        self.chk_scan_faces = QCheckBox("Detect faces after scanning")
        self.chk_scan_faces.setStyleSheet("color: #ccc;")
        self.chk_scan_faces.setChecked(False)
        self.chk_detect_dupes = QCheckBox("Find duplicate photos")
        self.chk_detect_dupes.setStyleSheet("color: #ccc;")
        self.chk_detect_dupes.setChecked(True)
        opts_layout.addWidget(self.chk_scan_faces)
        opts_layout.addWidget(self.chk_detect_dupes)
        left_layout.addWidget(opts_box)

        left_layout.addStretch()
        splitter.addWidget(left)

        # ── Right panel: progress and log ─────────────────────────────────────
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setSpacing(10)
        right_layout.setContentsMargins(8, 0, 0, 0)

        status_label = QLabel("Status")
        status_label.setStyleSheet("font-weight: bold; color: #ccc; font-size: 13px;")
        right_layout.addWidget(status_label)

        # Stats cards
        stats_row = QHBoxLayout()
        self._stat_total = _StatCard("Total Photos", "0")
        self._stat_new = _StatCard("New Found", "0", "#4caf8a")
        self._stat_dupes = _StatCard("Duplicates", "0", "#e8a04a")
        self._stat_faces = _StatCard("Faces Found", "0", "#6a9fd8")
        for card in [self._stat_total, self._stat_new, self._stat_dupes, self._stat_faces]:
            stats_row.addWidget(card)
        right_layout.addLayout(stats_row)

        # Progress
        self.progress_label = QLabel("Ready to scan.")
        self.progress_label.setStyleSheet("color: #999; font-size: 12px;")
        right_layout.addWidget(self.progress_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setStyleSheet(
            "QProgressBar { border: 1px solid #333; border-radius: 4px; background: #1a1a1a; color: #ccc; text-align: center; height: 18px; }"
            "QProgressBar::chunk { background: #2a6496; border-radius: 3px; }"
        )
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        right_layout.addWidget(self.progress_bar)

        # Current file
        self.current_file_label = QLabel("")
        self.current_file_label.setStyleSheet("color: #555; font-size: 11px;")
        self.current_file_label.setWordWrap(True)
        right_layout.addWidget(self.current_file_label)

        # Log
        log_label = QLabel("Scan Log")
        log_label.setStyleSheet("font-weight: bold; color: #ccc; font-size: 12px; margin-top: 8px;")
        right_layout.addWidget(log_label)

        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setStyleSheet(
            "QTextEdit { background: #111; border: 1px solid #2a2a2a; color: #6a9; font-family: monospace; font-size: 11px; border-radius: 4px; }"
        )
        right_layout.addWidget(self.log_view, 1)

        splitter.addWidget(right)
        splitter.setSizes([320, 480])

        # ── Bottom buttons ────────────────────────────────────────────────────
        btn_bar = QHBoxLayout()
        self.btn_scan = QPushButton("▶  Start Scan")
        self.btn_scan.setStyleSheet(_btn_style(primary=True))
        self.btn_scan.setFixedHeight(38)
        self.btn_scan.setMinimumWidth(140)
        self.btn_scan.clicked.connect(self._start_scan)

        self.btn_pause = QPushButton("⏸  Pause")
        self.btn_pause.setStyleSheet(_btn_style())
        self.btn_pause.setFixedHeight(38)
        self.btn_pause.setEnabled(False)
        self.btn_pause.clicked.connect(self._pause_scan)

        self.btn_stop = QPushButton("⏹  Stop")
        self.btn_stop.setStyleSheet(_btn_style(danger=True))
        self.btn_stop.setFixedHeight(38)
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._stop_scan)

        btn_bar.addWidget(self.btn_scan)
        btn_bar.addWidget(self.btn_pause)
        btn_bar.addWidget(self.btn_stop)
        btn_bar.addStretch()
        layout.addLayout(btn_bar)

    # ── Folder management ─────────────────────────────────────────────────────

    def _add_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Select Folder to Scan")
        if path:
            self._add_folder_path(path)

    def _add_folder_path(self, path: str):
        # Avoid duplicates
        for i in range(self.folder_list.count()):
            if self.folder_list.item(i).text() == path:
                return
        self.folder_list.addItem(path)
        self._save_folder_list()

    def _remove_folder(self):
        for item in self.folder_list.selectedItems():
            self.folder_list.takeItem(self.folder_list.row(item))
        self._save_folder_list()

    def _save_folder_list(self):
        pass  # Persisted via config in main window

    def _refresh_folder_list(self):
        pass  # Populated by main window on init

    def get_folders(self) -> list[str]:
        return [self.folder_list.item(i).text() for i in range(self.folder_list.count())]

    def set_folders(self, folders: list[str]):
        self.folder_list.clear()
        for f in folders:
            self.folder_list.addItem(f)

    # ── Scan control ──────────────────────────────────────────────────────────

    def _start_scan(self):
        folders = self.get_folders()
        if not folders:
            self._log("No folders selected. Click '+ Add Folder' to add a scan location.")
            return
        if self._worker and self._worker.is_alive():
            return

        self.btn_scan.setEnabled(False)
        self.btn_pause.setEnabled(True)
        self.btn_stop.setEnabled(True)
        self.progress_bar.setValue(0)
        self._log(f"Starting scan of {len(folders)} folder(s)...")

        self._worker = ScanWorker(
            db=self.db,
            folders=folders,
            thumb_dir=self.thumb_dir,
            on_progress=self._signals.progress.emit,
            on_finished=self._signals.finished.emit,
            on_error=self._signals.error.emit,
        )
        self._worker.start()

    def _pause_scan(self):
        if not self._worker:
            return
        if self.btn_pause.text().startswith("⏸"):
            self._worker.pause()
            self.btn_pause.setText("▶  Resume")
            self._log("Scan paused.")
        else:
            self._worker.resume()
            self.btn_pause.setText("⏸  Pause")
            self._log("Scan resumed.")

    def _stop_scan(self):
        if self._worker:
            self._worker.stop()
            self._log("Stopping scan…")
        self._reset_buttons()

    def _reset_buttons(self):
        self.btn_scan.setEnabled(True)
        self.btn_pause.setEnabled(False)
        self.btn_pause.setText("⏸  Pause")
        self.btn_stop.setEnabled(False)

    # ── Signals ───────────────────────────────────────────────────────────────

    def _on_progress(self, current: int, total: int, path: str):
        pct = int(current / total * 100) if total else 0
        self.progress_bar.setValue(pct)
        self.progress_label.setText(f"Scanning… {current:,} / {total:,} files")
        short = os.path.basename(path)
        self.current_file_label.setText(f"  {short}")

    def _on_finished(self, stats: dict):
        self._reset_buttons()
        self.progress_bar.setValue(100)
        self.progress_label.setText("Scan complete.")
        self.current_file_label.setText("")

        self._stat_total.set_value(str(stats.get("photos_found", 0)))
        self._stat_new.set_value(str(stats.get("new_photos", 0)))
        self._stat_dupes.set_value(str(self.db.get_stats().get("duplicate_groups", 0)))
        self._stat_faces.set_value(str(self.db.get_stats().get("total_faces", 0)))

        self._log(
            f"✓ Scan complete — "
            f"{stats.get('photos_found', 0):,} photos found, "
            f"{stats.get('new_photos', 0):,} new, "
            f"{stats.get('updated_photos', 0):,} updated."
        )
        self.scan_complete.emit(stats)

    def _on_error(self, msg: str):
        self._reset_buttons()
        self._log(f"✗ Error: {msg}")

    def _log(self, msg: str):
        from datetime import datetime
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_view.append(f"[{ts}]  {msg}")

    def refresh_stats(self):
        stats = self.db.get_stats()
        self._stat_total.set_value(str(stats["total_photos"]))
        self._stat_dupes.set_value(str(stats["duplicate_groups"]))
        self._stat_faces.set_value(str(stats["total_faces"]))


# ── Sub-widgets ───────────────────────────────────────────────────────────────

class _StatCard(QFrame):
    def __init__(self, label: str, value: str, color: str = "#7a9abf", parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            f"QFrame {{ background: #1a1a1a; border: 1px solid #2a2a2a; border-radius: 8px; }}"
        )
        self.setFixedHeight(72)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(2)
        self._val_label = QLabel(value)
        self._val_label.setStyleSheet(f"font-size: 22px; font-weight: bold; color: {color};")
        self._val_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl = QLabel(label)
        lbl.setStyleSheet("font-size: 10px; color: #666;")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._val_label)
        layout.addWidget(lbl)

    def set_value(self, v: str):
        self._val_label.setText(v)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _common_photo_dirs() -> list[tuple[str, str]]:
    import platform
    home = os.path.expanduser("~")
    system = platform.system()
    dirs = [("Pictures", os.path.join(home, "Pictures"))]
    if system == "Windows":
        dirs += [
            ("Desktop", os.path.join(home, "Desktop")),
            ("Downloads", os.path.join(home, "Downloads")),
            ("OneDrive", os.path.join(home, "OneDrive")),
        ]
    else:
        dirs += [
            ("Desktop", os.path.join(home, "Desktop")),
            ("Downloads", os.path.join(home, "Downloads")),
        ]
    return [(label, path) for label, path in dirs if os.path.exists(path)]


