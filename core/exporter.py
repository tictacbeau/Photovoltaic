"""Photo exporter — copies photos to a destination folder with optional renaming."""
import os
import shutil
import threading
from datetime import datetime


class ExportWorker(threading.Thread):
    """
    Copies a list of photo records to dest_dir.

    rename_mode:
        "original"  — keep original filename (append _1, _2 on collision)
        "date"      — YYYYMMDD_HHmmSS_original.ext using exif_date or date_added
        "sequence"  — 001_original.ext, 002_original.ext, …
    """

    def __init__(self, photos: list, dest_dir: str, rename_mode: str = "original",
                 on_progress=None, on_done=None):
        super().__init__(daemon=True)
        self.photos = photos
        self.dest_dir = dest_dir
        self.rename_mode = rename_mode
        self.on_progress = on_progress   # callable(current, total, filename)
        self.on_done = on_done           # callable(stats: dict)
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    def run(self):
        total = len(self.photos)
        copied = skipped = errors = 0
        os.makedirs(self.dest_dir, exist_ok=True)
        used_names: set[str] = set()

        for i, photo in enumerate(self.photos):
            if self._stop_event.is_set():
                break
            src = photo["file_path"]
            if not os.path.exists(src):
                skipped += 1
                if self.on_progress:
                    self.on_progress(i + 1, total, os.path.basename(src))
                continue
            dest_name = self._dest_name(photo, i + 1, used_names)
            used_names.add(dest_name)
            dest_path = os.path.join(self.dest_dir, dest_name)
            try:
                shutil.copy2(src, dest_path)
                copied += 1
            except OSError:
                errors += 1
            if self.on_progress:
                self.on_progress(i + 1, total, dest_name)

        if self.on_done:
            self.on_done({"copied": copied, "skipped": skipped, "errors": errors, "total": total})

    def _dest_name(self, photo: dict, seq: int, used: set) -> str:
        src = photo["file_path"]
        base = os.path.basename(src)
        name, ext = os.path.splitext(base)

        if self.rename_mode == "date":
            raw_date = photo.get("exif_date") or photo.get("date_added") or ""
            try:
                dt = datetime.fromisoformat(raw_date[:19])
                prefix = dt.strftime("%Y%m%d_%H%M%S")
            except (ValueError, TypeError):
                prefix = "nodate"
            candidate = f"{prefix}_{name}{ext}"
        elif self.rename_mode == "sequence":
            candidate = f"{seq:04d}_{name}{ext}"
        else:
            candidate = base

        # Resolve collisions
        if candidate not in used and not os.path.exists(os.path.join(self.dest_dir, candidate)):
            return candidate
        stem, sfx = os.path.splitext(candidate)
        counter = 1
        while True:
            new_candidate = f"{stem}_{counter}{sfx}"
            if new_candidate not in used and not os.path.exists(
                os.path.join(self.dest_dir, new_candidate)
            ):
                return new_candidate
            counter += 1
