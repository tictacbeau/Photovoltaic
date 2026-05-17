"""Filesystem scanner — walks directories, hashes files, reads EXIF, catalogs photos."""

import os
import hashlib
import threading
import logging
from datetime import datetime
from pathlib import Path
from typing import Callable

from PIL import Image, ExifTags
import imagehash

try:
    import exifread
    EXIFREAD_AVAILABLE = True
except ImportError:
    EXIFREAD_AVAILABLE = False

from core.database import Database

log = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".heic", ".heif",
    ".tiff", ".tif", ".bmp", ".gif",
    ".cr2", ".nef", ".arw", ".dng", ".orf", ".rw2", ".pef",
}

# Folders to always skip
SKIP_FOLDERS = {
    "windows", "program files", "program files (x86)",
    "programdata", "appdata", "$recycle.bin", "system volume information",
    "proc", "sys", "dev", "run", "snap", "boot",
    ".git", "__pycache__", "node_modules",
}


class ScanWorker(threading.Thread):
    """Background thread that scans folders and populates the database."""

    def __init__(
        self,
        db: Database,
        folders: list[str],
        thumb_dir: str,
        excluded_folders: list[str] = None,
        on_progress: Callable[[int, int, str], None] = None,
        on_finished: Callable[[dict], None] = None,
        on_error: Callable[[str], None] = None,
    ):
        super().__init__(daemon=True)
        self.db = db
        self.folders = folders
        self.thumb_dir = thumb_dir
        self.excluded_folders = {f.lower() for f in (excluded_folders or [])}
        self.on_progress = on_progress
        self.on_finished = on_finished
        self.on_error = on_error
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._pause_event.set()

    def stop(self):
        self._stop_event.set()

    def pause(self):
        self._pause_event.clear()

    def resume(self):
        self._pause_event.set()

    def run(self):
        try:
            self._run_scan()
        except Exception as exc:
            log.exception("Scanner error")
            if self.on_error:
                self.on_error(str(exc))

    def _run_scan(self):
        session_id = self.db.start_scan_session(self.folders)
        stats = {"photos_found": 0, "new_photos": 0, "updated_photos": 0, "missing_photos": 0}

        all_files = list(self._walk_all_files())
        total = len(all_files)

        for idx, file_path in enumerate(all_files):
            if self._stop_event.is_set():
                break
            self._pause_event.wait()

            if self.on_progress:
                self.on_progress(idx + 1, total, file_path)

            try:
                self._process_file(file_path, session_id, stats)
            except Exception as exc:
                log.warning("Failed to process %s: %s", file_path, exc)

        self._check_missing_files()
        self.db.finish_scan_session(session_id, stats)

        if self.on_finished:
            self.on_finished({**stats, "session_id": session_id, "total_found": total})

    def _walk_all_files(self):
        for folder in self.folders:
            if not os.path.isdir(folder):
                continue
            for root, dirs, files in os.walk(folder, followlinks=False):
                if self._stop_event.is_set():
                    return
                # Prune excluded/system dirs in-place
                dirs[:] = [
                    d for d in dirs
                    if d.lower() not in SKIP_FOLDERS
                    and os.path.join(root, d).lower() not in self.excluded_folders
                ]
                for fname in files:
                    ext = Path(fname).suffix.lower()
                    if ext in SUPPORTED_EXTENSIONS:
                        yield os.path.join(root, fname)

    def _process_file(self, file_path: str, session_id: int, stats: dict):
        stat = os.stat(file_path)
        mtime = datetime.fromtimestamp(stat.st_mtime).isoformat()
        size = stat.st_size
        ctime = datetime.fromtimestamp(stat.st_ctime).isoformat()

        existing = self.db.get_photo_by_path(file_path)
        if existing and existing["date_modified"] == mtime and existing["file_size"] == size:
            stats["photos_found"] += 1
            return

        sha256 = _hash_file(file_path)
        phash_str = _perceptual_hash(file_path)
        exif = _read_exif(file_path)
        dims = _read_dimensions(file_path)
        thumb = _make_thumbnail(file_path, self.thumb_dir, sha256)

        record = {
            "file_path": file_path,
            "file_name": os.path.basename(file_path),
            "file_size": size,
            "file_type": Path(file_path).suffix.lower().lstrip("."),
            "sha256_hash": sha256,
            "phash": phash_str,
            "width": dims[0],
            "height": dims[1],
            "date_created": ctime,
            "date_modified": mtime,
            "exif_date": exif.get("date"),
            "camera_make": exif.get("make"),
            "camera_model": exif.get("model"),
            "gps_lat": exif.get("gps_lat"),
            "gps_lon": exif.get("gps_lon"),
            "thumbnail_path": thumb,
            "scan_session_id": session_id,
            "is_missing": 0,
        }

        photo_id = self.db.upsert_photo(record)
        stats["photos_found"] += 1
        if existing:
            stats["updated_photos"] += 1
        else:
            stats["new_photos"] += 1

        # Register duplicate group by hash
        if sha256:
            group_id = self.db.get_or_create_duplicate_group(sha256)
            self.db.add_to_duplicate_group(group_id, photo_id)

    def _check_missing_files(self):
        for photo in self.db.get_all_photos():
            if not os.path.exists(photo["file_path"]):
                self.db.mark_missing(photo["id"])


# ── Pure helper functions ────────────────────────────────────────────────────

def _hash_file(path: str) -> str | None:
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def _perceptual_hash(path: str) -> str | None:
    try:
        with Image.open(path) as img:
            return str(imagehash.phash(img))
    except Exception:
        return None


def _read_dimensions(path: str) -> tuple[int, int]:
    try:
        with Image.open(path) as img:
            return img.size
    except Exception:
        return (0, 0)


def _read_exif(path: str) -> dict:
    result: dict = {}
    ext = Path(path).suffix.lower()

    # Pillow handles JPEG EXIF well
    try:
        with Image.open(path) as img:
            raw = img._getexif()
            if raw:
                for tag_id, value in raw.items():
                    tag = ExifTags.TAGS.get(tag_id, tag_id)
                    if tag == "DateTimeOriginal" and not result.get("date"):
                        try:
                            dt = datetime.strptime(str(value), "%Y:%m:%d %H:%M:%S")
                            result["date"] = dt.isoformat()
                        except ValueError:
                            pass
                    elif tag == "Make":
                        result["make"] = str(value).strip()
                    elif tag == "Model":
                        result["model"] = str(value).strip()
                    elif tag == "GPSInfo":
                        gps = _parse_gps(value)
                        result.update(gps)
    except Exception:
        pass

    # Fall back to exifread for RAW formats
    if EXIFREAD_AVAILABLE and not result.get("date") and ext in {
        ".cr2", ".nef", ".arw", ".dng", ".orf", ".rw2", ".pef"
    }:
        try:
            with open(path, "rb") as f:
                tags = exifread.process_file(f, stop_tag="EXIF DateTimeOriginal", details=False)
                dt_tag = tags.get("EXIF DateTimeOriginal") or tags.get("Image DateTime")
                if dt_tag:
                    try:
                        dt = datetime.strptime(str(dt_tag), "%Y:%m:%d %H:%M:%S")
                        result["date"] = dt.isoformat()
                    except ValueError:
                        pass
                if not result.get("make") and tags.get("Image Make"):
                    result["make"] = str(tags["Image Make"]).strip()
                if not result.get("model") and tags.get("Image Model"):
                    result["model"] = str(tags["Image Model"]).strip()
        except Exception:
            pass

    return result


def _parse_gps(gps_info: dict) -> dict:
    try:
        from PIL.ExifTags import GPSTAGS
        decoded = {GPSTAGS.get(k, k): v for k, v in gps_info.items()}

        def to_degrees(val):
            d, m, s = val
            return float(d) + float(m) / 60 + float(s) / 3600

        lat = to_degrees(decoded.get("GPSLatitude", (0, 0, 0)))
        lon = to_degrees(decoded.get("GPSLongitude", (0, 0, 0)))
        if decoded.get("GPSLatitudeRef") == "S":
            lat = -lat
        if decoded.get("GPSLongitudeRef") == "W":
            lon = -lon
        return {"gps_lat": lat, "gps_lon": lon}
    except Exception:
        return {}


def _make_thumbnail(path: str, thumb_dir: str, sha256: str, size: int = 256) -> str | None:
    if not sha256 or not thumb_dir:
        return None
    subdir = os.path.join(thumb_dir, sha256[:2])
    os.makedirs(subdir, exist_ok=True)
    thumb_path = os.path.join(subdir, f"{sha256}.jpg")
    if os.path.exists(thumb_path):
        return thumb_path
    try:
        with Image.open(path) as img:
            img = img.convert("RGB")
            img.thumbnail((size, size), Image.LANCZOS)
            img.save(thumb_path, "JPEG", quality=85, optimize=True)
        return thumb_path
    except Exception:
        return None
