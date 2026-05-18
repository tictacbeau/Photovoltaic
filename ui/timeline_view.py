"""Timeline View — photos grouped by year/month in chronological scroll."""
import calendar
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QSplitter, QListWidget, QListWidgetItem,
    QSizePolicy,
)
from PyQt6.QtCore import Qt

from ui.styles import btn_style
from ui.photo_grid import PhotoGrid
from ui.photo_detail import PhotoDetailDialog
from core.database import Database

MONTH_NAMES = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


class TimelineView(QWidget):
    def __init__(self, db: Database, parent=None):
        super().__init__(parent)
        self.db = db
        self._months = []          # [{year_month, year, month, count}]
        self._current_ym = None    # "YYYY-MM"
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

        title = QLabel("Timeline")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #c0d0e0; min-width: 80px;")
        tbar.addWidget(title)

        self.count_label = QLabel("No photos")
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

        # Left — month navigator
        left = QWidget()
        left.setFixedWidth(180)
        left.setStyleSheet("background: #111;")
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 0, 0)
        left_lay.setSpacing(0)

        nav_hdr = QLabel("  Months")
        nav_hdr.setStyleSheet(
            "color: #555; font-size: 11px; padding: 8px 12px; "
            "border-bottom: 1px solid #1a1a1a; background: #0d0d0d;"
        )
        nav_hdr.setFixedHeight(30)
        left_lay.addWidget(nav_hdr)

        self.month_list = QListWidget()
        self.month_list.setStyleSheet(
            "QListWidget { background: #111; border: none; outline: none; }"
            "QListWidget::item { color: #888; font-size: 12px; padding: 8px 14px; "
            "  border-bottom: 1px solid #1a1a1a; }"
            "QListWidget::item:selected { background: #152535; color: #b0d0f0; }"
            "QListWidget::item:hover { background: #161616; }"
        )
        self.month_list.currentRowChanged.connect(self._on_month_selected)
        left_lay.addWidget(self.month_list, 1)
        splitter.addWidget(left)

        # Right — photo grid + header
        right = QWidget()
        right.setStyleSheet("background: #141414;")
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(0, 0, 0, 0)
        right_lay.setSpacing(0)

        self.month_header = QLabel()
        self.month_header.setStyleSheet(
            "font-size: 18px; font-weight: bold; color: #7ab8e0; "
            "padding: 14px 20px 10px 20px; background: #141414; "
            "border-bottom: 1px solid #1e1e1e;"
        )
        self.month_header.hide()
        right_lay.addWidget(self.month_header)

        self.grid = PhotoGrid()
        self.grid.photo_activated.connect(self._on_photo_activated)
        right_lay.addWidget(self.grid, 1)

        self.empty_label = QLabel("Select a month from the left panel")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet(
            "color: #333; font-size: 14px; background: #141414;"
        )
        right_lay.addWidget(self.empty_label)

        splitter.addWidget(right)
        root.addWidget(splitter, 1)

    # ── Public ───────────────────────────────────────────────────────────────

    def refresh(self):
        self._months = self.db.get_timeline_months()
        total = sum(m["count"] for m in self._months)
        n = len(self._months)
        self.count_label.setText(
            f"{total:,} photos across {n} month{'s' if n != 1 else ''}" if n
            else "No photos"
        )
        self.month_list.blockSignals(True)
        self.month_list.clear()
        prev_year = None
        for m in self._months:
            yr, mo = m["year"], m["month"]
            # Year separator item
            if yr != prev_year:
                sep = QListWidgetItem(str(yr))
                sep.setFlags(Qt.ItemFlag.NoItemFlags)
                sep.setForeground(Qt.GlobalColor.darkGray)
                f = sep.font()
                f.setBold(True)
                f.setPointSize(10)
                sep.setFont(f)
                sep.setData(Qt.ItemDataRole.UserRole, None)
                self.month_list.addItem(sep)
                prev_year = yr
            name = MONTH_NAMES[mo] if 1 <= mo <= 12 else f"Month {mo}"
            item = QListWidgetItem(f"  {name}  ({m['count']})")
            item.setData(Qt.ItemDataRole.UserRole, m["year_month"])
            self.month_list.addItem(item)
        self.month_list.blockSignals(False)

        # Restore or auto-select first real month
        if self._current_ym:
            for i in range(self.month_list.count()):
                if self.month_list.item(i).data(Qt.ItemDataRole.UserRole) == self._current_ym:
                    self.month_list.setCurrentRow(i)
                    return
        self._select_first_real_month()

    # ── Internal ─────────────────────────────────────────────────────────────

    def _select_first_real_month(self):
        for i in range(self.month_list.count()):
            if self.month_list.item(i).data(Qt.ItemDataRole.UserRole) is not None:
                self.month_list.setCurrentRow(i)
                return

    def _on_month_selected(self, row: int):
        if row < 0:
            return
        item = self.month_list.item(row)
        if not item:
            return
        ym = item.data(Qt.ItemDataRole.UserRole)
        if ym is None:
            return  # year-separator row — ignore
        self._current_ym = ym
        self._load_month(ym)

    def _load_month(self, ym: str):
        try:
            yr, mo = int(ym[:4]), int(ym[5:7])
        except (ValueError, IndexError):
            return
        name = MONTH_NAMES[mo] if 1 <= mo <= 12 else f"Month {mo}"
        self.month_header.setText(f"{name} {yr}")
        self.month_header.show()
        self.empty_label.hide()
        photos = self.db.get_photos_for_month(yr, mo)
        self.grid.set_photos(photos)

    def _on_photo_activated(self, photo_id: int):
        all_ids = self.grid.photo_ids()
        dlg = PhotoDetailDialog(self.db, photo_id, all_ids, parent=self)
        dlg.exec()
