"""Image utility helpers shared across the app."""

import os
from PIL import Image


def load_thumbnail(path: str, size: tuple[int, int] = (200, 200)) -> Image.Image | None:
    """Load an image and return a thumbnail-sized copy, or None on failure."""
    if not path or not os.path.exists(path):
        return None
    try:
        img = Image.open(path)
        img = img.convert("RGB")
        img.thumbnail(size, Image.LANCZOS)
        return img
    except Exception:
        return None


def pil_to_qpixmap(pil_img: Image.Image):
    """Convert a PIL Image to a QPixmap (requires PyQt6)."""
    from PyQt6.QtGui import QImage, QPixmap
    import io
    buf = io.BytesIO()
    pil_img.save(buf, format="PNG")
    buf.seek(0)
    qimg = QImage.fromData(buf.read())
    return QPixmap.fromImage(qimg)


def placeholder_pixmap(size: tuple[int, int] = (200, 200), color: str = "#2d2d2d"):
    """Return a solid-colour QPixmap as a placeholder."""
    from PyQt6.QtGui import QPixmap, QColor
    from PyQt6.QtCore import Qt
    px = QPixmap(size[0], size[1])
    px.fill(QColor(color))
    return px
