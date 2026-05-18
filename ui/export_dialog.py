"""Export Dialog — copy an album or smart album's photos to a folder."""
import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QLineEdit, QProgressBar, QFileDialog,
    QMessageBox, QRadioButton, QButtonGroup, QGroupBox,
)
from PyQt6.QtCore import Qt, pyqtSignal, QObject

from ui.styles import btn_style
from core.database import Database
from core.exporter import ExportWorker


class _WorkerSignals(QObject):
    progress = pyqtSignal(int, int, str)   # current, total, filename
    done = pyqtSignal(dict)                # stats


class ExportDialog(QDialog):
    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        self._worker = None
        self.setWindowTitle("Export Photos")
        self.setMinimumWidth(520)
        self.setStyleSheet("QDialog { background: #141414; } QLabel { color: #ccc; }")
        self._build_ui()
        self._populate_sources()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(14)
        root.setContentsMargins(20, 20, 20, 20)

        # ── Source ───────────────────────────────────────────────────────────
        src_group = QGroupBox("Source")
        src_group.setStyleSheet(
            "QGroupBox { color: #7ab8e0; border: 1px solid #2a2a2a; border-radius: 4px; "
            "margin-top: 8px; padding-top: 8px; } "
            "QGroupBox::title { subcontrol-origin: margin; padding: 0 6px; }"
        )
        src_lay = QVBoxLayout(src_group)

        src_row = QHBoxLayout()
        src_type_lbl = QLabel("Collection:")
        src_type_lbl.setFixedWidth(90)
        src_row.addWidget(src_type_lbl)
        self.src_combo = QComboBox()
        self.src_combo.setStyleSheet(
            "QComboBox { background: #1a1a1a; color: #ccc; border: 1px solid #333; "
            "border-radius: 4px; padding: 4px 8px; }"
            "QComboBox QAbstractItemView { background: #1e1e1e; color: #ccc; "
            "selection-background-color: #2a4a6e; }"
        )
        src_row.addWidget(self.src_combo, 1)
        src_lay.addLayout(src_row)

        self.photo_count_lbl = QLabel("0 photos selected")
        self.photo_count_lbl.setStyleSheet("color: #555; font-size: 11px;")
        src_lay.addWidget(self.photo_count_lbl)
        self.src_combo.currentIndexChanged.connect(self._on_source_changed)
        root.addWidget(src_group)

        # ── Destination ──────────────────────────────────────────────────────
        dest_group = QGroupBox("Destination")
        dest_group.setStyleSheet(src_group.styleSheet())
        dest_lay = QVBoxLayout(dest_group)

        dest_row = QHBoxLayout()
        dest_lbl = QLabel("Folder:")
        dest_lbl.setFixedWidth(90)
        dest_row.addWidget(dest_lbl)
        self.dest_edit = QLineEdit()
        self.dest_edit.setPlaceholderText("Choose destination folder…")
        self.dest_edit.setStyleSheet(
            "QLineEdit { background: #1a1a1a; color: #ccc; border: 1px solid #333; "
            "border-radius: 4px; padding: 4px 8px; }"
        )
        dest_row.addWidget(self.dest_edit, 1)
        browse_btn = QPushButton("Browse…")
        browse_btn.setStyleSheet(btn_style(small=True))
        browse_btn.setFixedHeight(28)
        browse_btn.clicked.connect(self._browse)
        dest_row.addWidget(browse_btn)
        dest_lay.addLayout(dest_row)
        root.addWidget(dest_group)

        # ── Rename mode ──────────────────────────────────────────────────────
        rename_group = QGroupBox("File naming")
        rename_group.setStyleSheet(src_group.styleSheet())
        rename_lay = QVBoxLayout(rename_group)
        self._rename_group = QButtonGroup(self)
        for label, mode in [
            ("Keep original filenames", "original"),
            ("Prefix with date  (20230815_123000_photo.jpg)", "date"),
            ("Prefix with sequence number  (0001_photo.jpg)", "sequence"),
        ]:
            rb = QRadioButton(label)
            rb.setStyleSheet("color: #aaa; font-size: 12px;")
            rb.setProperty("rename_mode", mode)
            self._rename_group.addButton(rb)
            rename_lay.addWidget(rb)
            if mode == "original":
                rb.setChecked(True)
        root.addWidget(rename_group)

        # ── Progress ─────────────────────────────────────────────────────────
        self.progress_bar = QProgressBar()
        self.progress_bar.setStyleSheet(
            "QProgressBar { background: #1a1a1a; border: 1px solid #333; border-radius: 4px; "
            "color: #ccc; text-align: center; height: 20px; }"
            "QProgressBar::chunk { background: #2a6aaf; border-radius: 3px; }"
        )
        self.progress_bar.hide()
        root.addWidget(self.progress_bar)

        self.status_lbl = QLabel("")
        self.status_lbl.setStyleSheet("color: #555; font-size: 11px;")
        self.status_lbl.hide()
        root.addWidget(self.status_lbl)

        # ── Buttons ──────────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setStyleSheet(btn_style(small=True))
        self.cancel_btn.setFixedHeight(30)
        self.cancel_btn.clicked.connect(self._on_cancel)
        self.export_btn = QPushButton("Export")
        self.export_btn.setStyleSheet(btn_style(small=True, primary=True))
        self.export_btn.setFixedHeight(30)
        self.export_btn.clicked.connect(self._start_export)
        btn_row.addWidget(self.cancel_btn)
        btn_row.addWidget(self.export_btn)
        root.addLayout(btn_row)

    # ── Population ───────────────────────────────────────────────────────────

    def _populate_sources(self):
        self.src_combo.blockSignals(True)
        self.src_combo.clear()
        # Regular albums
        for a in self.db.get_all_albums():
            self.src_combo.addItem(
                f"📁 {a['name']}  ({a['photo_count']} photos)",
                ("album", a["id"]),
            )
        # Smart albums
        for a in self.db.get_all_smart_albums():
            self.src_combo.addItem(
                f"{a['icon']} {a['name']}",
                ("smart", a["id"]),
            )
        self.src_combo.blockSignals(False)
        self._on_source_changed()

    def _on_source_changed(self):
        data = self.src_combo.currentData()
        if not data:
            self.photo_count_lbl.setText("0 photos")
            return
        kind, src_id = data
        if kind == "album":
            n = self.db.count_album_photos(src_id)
        else:
            n = len(self.db.get_smart_album_photos(src_id))
        self.photo_count_lbl.setText(f"{n:,} photo{'s' if n != 1 else ''} will be exported")

    def _browse(self):
        folder = QFileDialog.getExistingDirectory(self, "Choose Destination Folder")
        if folder:
            self.dest_edit.setText(folder)

    # ── Export ───────────────────────────────────────────────────────────────

    def _get_photos(self):
        data = self.src_combo.currentData()
        if not data:
            return []
        kind, src_id = data
        if kind == "album":
            return self.db.get_album_photos(src_id)
        else:
            return self.db.get_smart_album_photos(src_id)

    def _get_rename_mode(self) -> str:
        for btn in self._rename_group.buttons():
            if btn.isChecked():
                return btn.property("rename_mode")
        return "original"

    def _start_export(self):
        dest = self.dest_edit.text().strip()
        if not dest:
            QMessageBox.warning(self, "No Destination", "Please choose a destination folder.")
            return
        photos = self._get_photos()
        if not photos:
            QMessageBox.information(self, "Nothing to Export", "The selected collection has no photos.")
            return

        self.export_btn.setEnabled(False)
        self.progress_bar.setMaximum(len(photos))
        self.progress_bar.setValue(0)
        self.progress_bar.show()
        self.status_lbl.show()

        signals = _WorkerSignals()
        signals.progress.connect(self._on_progress)
        signals.done.connect(self._on_done)
        self._signals = signals  # keep alive

        rename_mode = self._get_rename_mode()
        self._worker = ExportWorker(
            photos=photos,
            dest_dir=dest,
            rename_mode=rename_mode,
            on_progress=lambda cur, tot, fn: signals.progress.emit(cur, tot, fn),
            on_done=lambda stats: signals.done.emit(stats),
        )
        self._worker.start()

    def _on_progress(self, current: int, total: int, filename: str):
        self.progress_bar.setValue(current)
        self.status_lbl.setText(f"Copying {filename}…")

    def _on_done(self, stats: dict):
        self.export_btn.setEnabled(True)
        self.status_lbl.hide()
        self.progress_bar.hide()
        msg = (
            f"Export complete.\n\n"
            f"  Copied:  {stats['copied']:,}\n"
            f"  Skipped: {stats['skipped']:,}  (file not found)\n"
            f"  Errors:  {stats['errors']:,}"
        )
        QMessageBox.information(self, "Export Done", msg)

    def _on_cancel(self):
        if self._worker and self._worker.is_alive():
            self._worker.stop()
        self.reject()
