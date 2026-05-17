"""Reusable lazy-loading photo grid widget."""
import os
from PyQt6.QtWidgets import QListWidget, QListWidgetItem, QAbstractItemView
from PyQt6.QtCore import Qt, QSize, QRunnable, QThreadPool, QObject, pyqtSignal
from PyQt6.QtGui import QIcon, QPixmap, QImage
from utils.image_utils import placeholder_pixmap

THUMB_SIZE = 180


class _ThumbSignals(QObject):
    # QImage is thread-safe; QPixmap is NOT — convert only in main thread
    loaded = pyqtSignal(int, QImage)


class _ThumbTask(QRunnable):
    def __init__(self, photo_id: int, thumb_path: str, signals: _ThumbSignals):
        super().__init__()
        self.photo_id = photo_id
        self.thumb_path = thumb_path
        self.signals = signals
        self.setAutoDelete(True)

    def run(self):
        try:
            img = QImage(self.thumb_path)
            if not img.isNull():
                img = img.scaled(
                    THUMB_SIZE, THUMB_SIZE,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self.signals.loaded.emit(self.photo_id, img)
        except Exception:
            pass


class PhotoGrid(QListWidget):
    """Scrollable photo grid with background thumbnail loading."""
    photo_activated = pyqtSignal(int)    # double-click → photo_id
    selection_changed = pyqtSignal(int)  # single-click → photo_id (-1 if none)

    def __init__(self, thumb_size: int = THUMB_SIZE, parent=None):
        super().__init__(parent)
        self._thumb_size = thumb_size
        self._pool = QThreadPool.globalInstance()
        self._placeholder = QIcon(placeholder_pixmap((thumb_size, thumb_size)))
        self._id_map: dict[int, int] = {}      # photo_id → row index
        self._pending_signals: dict[int, _ThumbSignals] = {}  # keep alive until delivered
        self._setup()

    def _setup(self):
        self.setViewMode(QListWidget.ViewMode.IconMode)
        self.setIconSize(QSize(self._thumb_size, self._thumb_size))
        self.setGridSize(QSize(self._thumb_size + 24, self._thumb_size + 40))
        self.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setUniformItemSizes(True)
        self.setSpacing(4)
        self.setWordWrap(True)
        self.setStyleSheet(
            "QListWidget { background: #141414; border: none; outline: none; }"
            "QListWidget::item { color: #777; font-size: 10px; border-radius: 4px; padding-top: 2px; }"
            "QListWidget::item:selected { background: #1e3a5f; color: #b0d0f0; }"
            "QListWidget::item:hover { background: #1c1c1c; }"
        )
        self.itemActivated.connect(self._on_activated)
        self.itemSelectionChanged.connect(self._on_selection_changed)

    def set_photos(self, rows: list):
        self.clear()
        self._id_map.clear()
        self._pending_signals.clear()
        for idx, row in enumerate(rows):
            self._add_item(row, idx)

    def append_photos(self, rows: list):
        start = self.count()
        for idx, row in enumerate(rows):
            self._add_item(row, start + idx)

    def _add_item(self, row, idx: int):
        pid = row["id"]
        name = os.path.basename(row["file_path"])
        item = QListWidgetItem(self._placeholder, name)
        item.setData(Qt.ItemDataRole.UserRole, pid)
        item.setToolTip(row["file_path"])
        self.addItem(item)
        self._id_map[pid] = idx
        thumb = row["thumbnail_path"]
        if thumb and os.path.exists(str(thumb)):
            signals = _ThumbSignals()
            signals.loaded.connect(self._on_thumb_loaded)
            # Keep reference alive until the signal fires
            self._pending_signals[pid] = signals
            task = _ThumbTask(pid, str(thumb), signals)
            self._pool.start(task)

    def _on_thumb_loaded(self, photo_id: int, img: QImage):
        # Convert QImage → QPixmap here, safely on the main thread
        px = QPixmap.fromImage(img)
        self._pending_signals.pop(photo_id, None)
        idx = self._id_map.get(photo_id)
        if idx is not None and idx < self.count():
            item = self.item(idx)
            if item and item.data(Qt.ItemDataRole.UserRole) == photo_id:
                item.setIcon(QIcon(px))

    def _on_activated(self, item: QListWidgetItem):
        pid = item.data(Qt.ItemDataRole.UserRole)
        if pid is not None:
            self.photo_activated.emit(pid)

    def _on_selection_changed(self):
        items = self.selectedItems()
        if items:
            self.selection_changed.emit(items[0].data(Qt.ItemDataRole.UserRole))
        else:
            self.selection_changed.emit(-1)

    def selected_photo_id(self) -> int | None:
        items = self.selectedItems()
        return items[0].data(Qt.ItemDataRole.UserRole) if items else None

    def photo_ids(self) -> list[int]:
        return [self.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.count())]
