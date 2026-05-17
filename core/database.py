"""SQLite database layer — schema creation, CRUD helpers, connection management."""

import sqlite3
import os
import json
import threading
from datetime import datetime
from pathlib import Path


_local = threading.local()


def get_connection(db_path: str) -> sqlite3.Connection:
    """Return a thread-local connection to the database."""
    if not hasattr(_local, "connections"):
        _local.connections = {}
    if db_path not in _local.connections:
        conn = sqlite3.connect(db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA cache_size=-32000")
        _local.connections[db_path] = conn
    return _local.connections[db_path]


SCHEMA = """
CREATE TABLE IF NOT EXISTS photos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path       TEXT    UNIQUE NOT NULL,
    file_name       TEXT    NOT NULL,
    file_size       INTEGER,
    file_type       TEXT,
    sha256_hash     TEXT,
    phash           TEXT,
    width           INTEGER,
    height          INTEGER,
    date_created    TEXT,
    date_modified   TEXT,
    exif_date       TEXT,
    camera_make     TEXT,
    camera_model    TEXT,
    gps_lat         REAL,
    gps_lon         REAL,
    thumbnail_path  TEXT,
    scan_session_id INTEGER,
    date_added      TEXT    DEFAULT CURRENT_TIMESTAMP,
    is_missing      INTEGER DEFAULT 0,
    FOREIGN KEY (scan_session_id) REFERENCES scan_sessions(id)
);

CREATE INDEX IF NOT EXISTS idx_photos_hash   ON photos(sha256_hash);
CREATE INDEX IF NOT EXISTS idx_photos_phash  ON photos(phash);
CREATE INDEX IF NOT EXISTS idx_photos_path   ON photos(file_path);
CREATE INDEX IF NOT EXISTS idx_photos_exif   ON photos(exif_date);

CREATE TABLE IF NOT EXISTS people (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    name                    TEXT    NOT NULL DEFAULT 'Unknown Person',
    confirmed_count         INTEGER DEFAULT 0,
    match_threshold         REAL    DEFAULT 0.6,
    representative_thumbnail TEXT,
    date_created            TEXT    DEFAULT CURRENT_TIMESTAMP,
    notes                   TEXT,
    relationship            TEXT,
    is_hidden               INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS faces (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    photo_id        INTEGER NOT NULL,
    person_id       INTEGER,
    bbox_top        INTEGER,
    bbox_right      INTEGER,
    bbox_bottom     INTEGER,
    bbox_left       INTEGER,
    embedding       BLOB,
    confidence      REAL    DEFAULT 0.0,
    is_confirmed    INTEGER DEFAULT 0,
    is_ignored      INTEGER DEFAULT 0,
    thumbnail_path  TEXT,
    date_detected   TEXT    DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (photo_id)  REFERENCES photos(id) ON DELETE CASCADE,
    FOREIGN KEY (person_id) REFERENCES people(id)
);

CREATE INDEX IF NOT EXISTS idx_faces_photo   ON faces(photo_id);
CREATE INDEX IF NOT EXISTS idx_faces_person  ON faces(person_id);
CREATE INDEX IF NOT EXISTS idx_faces_confirmed ON faces(is_confirmed);

CREATE TABLE IF NOT EXISTS duplicate_groups (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    group_hash      TEXT    UNIQUE NOT NULL,
    master_photo_id INTEGER,
    date_created    TEXT    DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (master_photo_id) REFERENCES photos(id)
);

CREATE TABLE IF NOT EXISTS duplicate_members (
    group_id        INTEGER NOT NULL,
    photo_id        INTEGER NOT NULL,
    is_master       INTEGER DEFAULT 0,
    PRIMARY KEY (group_id, photo_id),
    FOREIGN KEY (group_id)  REFERENCES duplicate_groups(id),
    FOREIGN KEY (photo_id)  REFERENCES photos(id)
);

CREATE TABLE IF NOT EXISTS scan_sessions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    start_time      TEXT,
    end_time        TEXT,
    folders_scanned TEXT,
    photos_found    INTEGER DEFAULT 0,
    new_photos      INTEGER DEFAULT 0,
    updated_photos  INTEGER DEFAULT 0,
    missing_photos  INTEGER DEFAULT 0,
    faces_detected  INTEGER DEFAULT 0,
    status          TEXT    DEFAULT 'running'
);

CREATE TABLE IF NOT EXISTS audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT    DEFAULT CURRENT_TIMESTAMP,
    action      TEXT    NOT NULL,
    photo_id    INTEGER,
    face_id     INTEGER,
    person_id   INTEGER,
    details     TEXT
);
"""


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._init_schema()

    def _conn(self) -> sqlite3.Connection:
        return get_connection(self.db_path)

    def _init_schema(self):
        conn = self._conn()
        conn.executescript(SCHEMA)
        conn.commit()

    # ── Photos ──────────────────────────────────────────────────────────────

    def upsert_photo(self, data: dict) -> int:
        conn = self._conn()
        cols = list(data.keys())
        placeholders = ", ".join(["?"] * len(cols))
        updates = ", ".join(f"{c}=excluded.{c}" for c in cols if c != "file_path")
        sql = f"""
            INSERT INTO photos ({", ".join(cols)}) VALUES ({placeholders})
            ON CONFLICT(file_path) DO UPDATE SET {updates}
        """
        cur = conn.execute(sql, list(data.values()))
        conn.commit()
        if cur.lastrowid:
            return cur.lastrowid
        row = conn.execute("SELECT id FROM photos WHERE file_path=?", (data["file_path"],)).fetchone()
        return row["id"] if row else -1

    def get_photo(self, photo_id: int) -> sqlite3.Row | None:
        return self._conn().execute("SELECT * FROM photos WHERE id=?", (photo_id,)).fetchone()

    def get_photo_by_path(self, path: str) -> sqlite3.Row | None:
        return self._conn().execute("SELECT * FROM photos WHERE file_path=?", (path,)).fetchone()

    def get_photo_by_hash(self, sha256: str) -> sqlite3.Row | None:
        return self._conn().execute("SELECT * FROM photos WHERE sha256_hash=?", (sha256,)).fetchone()

    def get_all_photos(self, limit: int = 0, offset: int = 0) -> list:
        sql = "SELECT * FROM photos WHERE is_missing=0 ORDER BY exif_date DESC, date_added DESC"
        if limit:
            sql += f" LIMIT {limit} OFFSET {offset}"
        return self._conn().execute(sql).fetchall()

    def count_photos(self) -> int:
        return self._conn().execute("SELECT COUNT(*) FROM photos WHERE is_missing=0").fetchone()[0]

    def mark_missing(self, photo_id: int):
        conn = self._conn()
        conn.execute("UPDATE photos SET is_missing=1 WHERE id=?", (photo_id,))
        conn.commit()

    def search_photos(self, query: str = "", filters: dict = None) -> list:
        conditions = ["p.is_missing=0"]
        params = []
        if query:
            conditions.append("(p.file_name LIKE ? OR p.camera_model LIKE ?)")
            params += [f"%{query}%", f"%{query}%"]
        if filters:
            if filters.get("date_from"):
                conditions.append("COALESCE(p.exif_date, p.date_created) >= ?")
                params.append(filters["date_from"])
            if filters.get("date_to"):
                conditions.append("COALESCE(p.exif_date, p.date_created) <= ?")
                params.append(filters["date_to"])
            if filters.get("has_faces") is not None:
                if filters["has_faces"]:
                    conditions.append("EXISTS (SELECT 1 FROM faces f WHERE f.photo_id=p.id AND f.is_ignored=0)")
                else:
                    conditions.append("NOT EXISTS (SELECT 1 FROM faces f WHERE f.photo_id=p.id)")
            if filters.get("person_id"):
                conditions.append(
                    "EXISTS (SELECT 1 FROM faces f WHERE f.photo_id=p.id AND f.person_id=?)"
                )
                params.append(filters["person_id"])
        where = " AND ".join(conditions)
        sql = f"SELECT p.* FROM photos p WHERE {where} ORDER BY COALESCE(p.exif_date, p.date_added) DESC"
        return self._conn().execute(sql, params).fetchall()

    # ── People ───────────────────────────────────────────────────────────────

    def create_person(self, name: str = "Unknown Person", relationship: str = "") -> int:
        conn = self._conn()
        cur = conn.execute(
            "INSERT INTO people (name, relationship) VALUES (?, ?)", (name, relationship)
        )
        conn.commit()
        return cur.lastrowid

    def get_person(self, person_id: int) -> sqlite3.Row | None:
        return self._conn().execute("SELECT * FROM people WHERE id=?", (person_id,)).fetchone()

    def get_all_people(self, include_hidden: bool = False) -> list:
        sql = "SELECT * FROM people"
        if not include_hidden:
            sql += " WHERE is_hidden=0"
        sql += " ORDER BY confirmed_count DESC, name ASC"
        return self._conn().execute(sql).fetchall()

    def update_person(self, person_id: int, **kwargs):
        conn = self._conn()
        sets = ", ".join(f"{k}=?" for k in kwargs)
        conn.execute(f"UPDATE people SET {sets} WHERE id=?", list(kwargs.values()) + [person_id])
        conn.commit()

    def refresh_person_stats(self, person_id: int):
        """Recount confirmed faces and update adaptive threshold."""
        conn = self._conn()
        count = conn.execute(
            "SELECT COUNT(*) FROM faces WHERE person_id=? AND is_confirmed=1 AND is_ignored=0",
            (person_id,),
        ).fetchone()[0]
        threshold = _adaptive_threshold(count)
        conn.execute(
            "UPDATE people SET confirmed_count=?, match_threshold=? WHERE id=?",
            (count, threshold, person_id),
        )
        conn.commit()

    def merge_people(self, source_id: int, target_id: int):
        """Merge all faces from source person into target person."""
        conn = self._conn()
        conn.execute(
            "UPDATE faces SET person_id=?, is_confirmed=0 WHERE person_id=?",
            (target_id, source_id),
        )
        conn.execute("DELETE FROM people WHERE id=?", (source_id,))
        conn.commit()
        self.refresh_person_stats(target_id)
        self.log("merge_people", person_id=target_id, details=f"merged person {source_id} into {target_id}")

    # ── Faces ────────────────────────────────────────────────────────────────

    def insert_face(self, data: dict) -> int:
        conn = self._conn()
        cols = list(data.keys())
        placeholders = ", ".join(["?"] * len(cols))
        cur = conn.execute(
            f"INSERT INTO faces ({', '.join(cols)}) VALUES ({placeholders})", list(data.values())
        )
        conn.commit()
        return cur.lastrowid

    def get_faces_for_photo(self, photo_id: int) -> list:
        return self._conn().execute(
            "SELECT * FROM faces WHERE photo_id=? AND is_ignored=0", (photo_id,)
        ).fetchall()

    def get_faces_for_person(self, person_id: int, confirmed_only: bool = False) -> list:
        sql = "SELECT f.*, p.file_path, p.thumbnail_path as photo_thumb FROM faces f JOIN photos p ON f.photo_id=p.id WHERE f.person_id=?"
        params = [person_id]
        if confirmed_only:
            sql += " AND f.is_confirmed=1"
        sql += " AND f.is_ignored=0 ORDER BY f.date_detected DESC"
        return self._conn().execute(sql, params).fetchall()

    def get_unassigned_faces(self) -> list:
        return self._conn().execute(
            "SELECT f.*, p.file_path FROM faces f JOIN photos p ON f.photo_id=p.id "
            "WHERE f.person_id IS NULL AND f.is_ignored=0"
        ).fetchall()

    def confirm_face(self, face_id: int, person_id: int):
        conn = self._conn()
        conn.execute(
            "UPDATE faces SET person_id=?, is_confirmed=1 WHERE id=?", (person_id, face_id)
        )
        conn.commit()
        self.refresh_person_stats(person_id)
        self.log("confirm_face", face_id=face_id, person_id=person_id)

    def reject_face(self, face_id: int, person_id: int):
        """Mark face as not this person (clear assignment but don't delete)."""
        conn = self._conn()
        conn.execute(
            "UPDATE faces SET person_id=NULL, is_confirmed=0 WHERE id=? AND person_id=?",
            (face_id, person_id),
        )
        conn.commit()
        self.refresh_person_stats(person_id)

    def ignore_face(self, face_id: int):
        conn = self._conn()
        conn.execute("UPDATE faces SET is_ignored=1, person_id=NULL WHERE id=?", (face_id,))
        conn.commit()

    def get_all_confirmed_embeddings(self) -> dict:
        """Return {person_id: [embedding_bytes, ...]} for all confirmed faces."""
        rows = self._conn().execute(
            "SELECT person_id, embedding FROM faces WHERE is_confirmed=1 AND is_ignored=0 AND embedding IS NOT NULL"
        ).fetchall()
        result: dict[int, list] = {}
        for row in rows:
            pid = row["person_id"]
            if pid not in result:
                result[pid] = []
            result[pid].append(row["embedding"])
        return result

    # ── Scan sessions ────────────────────────────────────────────────────────

    def start_scan_session(self, folders: list) -> int:
        conn = self._conn()
        cur = conn.execute(
            "INSERT INTO scan_sessions (start_time, folders_scanned, status) VALUES (?, ?, 'running')",
            (datetime.now().isoformat(), json.dumps(folders)),
        )
        conn.commit()
        return cur.lastrowid

    def update_scan_session(self, session_id: int, **kwargs):
        conn = self._conn()
        sets = ", ".join(f"{k}=?" for k in kwargs)
        conn.execute(f"UPDATE scan_sessions SET {sets} WHERE id=?", list(kwargs.values()) + [session_id])
        conn.commit()

    def finish_scan_session(self, session_id: int, stats: dict):
        stats["end_time"] = datetime.now().isoformat()
        stats["status"] = "completed"
        self.update_scan_session(session_id, **stats)

    def get_last_scan_session(self) -> sqlite3.Row | None:
        return self._conn().execute(
            "SELECT * FROM scan_sessions ORDER BY id DESC LIMIT 1"
        ).fetchone()

    # ── Duplicates ───────────────────────────────────────────────────────────

    def get_or_create_duplicate_group(self, group_hash: str) -> int:
        conn = self._conn()
        row = conn.execute(
            "SELECT id FROM duplicate_groups WHERE group_hash=?", (group_hash,)
        ).fetchone()
        if row:
            return row["id"]
        cur = conn.execute(
            "INSERT INTO duplicate_groups (group_hash) VALUES (?)", (group_hash,)
        )
        conn.commit()
        return cur.lastrowid

    def add_to_duplicate_group(self, group_id: int, photo_id: int, is_master: bool = False):
        conn = self._conn()
        conn.execute(
            "INSERT OR IGNORE INTO duplicate_members (group_id, photo_id, is_master) VALUES (?, ?, ?)",
            (group_id, photo_id, 1 if is_master else 0),
        )
        conn.commit()

    def get_duplicate_groups(self) -> list:
        return self._conn().execute(
            "SELECT dg.*, COUNT(dm.photo_id) as member_count "
            "FROM duplicate_groups dg "
            "JOIN duplicate_members dm ON dg.id=dm.group_id "
            "GROUP BY dg.id HAVING member_count > 1"
        ).fetchall()

    def get_duplicate_group_photos(self, group_id: int) -> list:
        return self._conn().execute(
            "SELECT p.*, dm.is_master FROM photos p "
            "JOIN duplicate_members dm ON p.id=dm.photo_id "
            "WHERE dm.group_id=?",
            (group_id,),
        ).fetchall()

    # ── Stats ────────────────────────────────────────────────────────────────

    def get_stats(self) -> dict:
        conn = self._conn()
        return {
            "total_photos": conn.execute("SELECT COUNT(*) FROM photos WHERE is_missing=0").fetchone()[0],
            "missing_photos": conn.execute("SELECT COUNT(*) FROM photos WHERE is_missing=1").fetchone()[0],
            "total_people": conn.execute("SELECT COUNT(*) FROM people WHERE is_hidden=0").fetchone()[0],
            "total_faces": conn.execute("SELECT COUNT(*) FROM faces WHERE is_ignored=0").fetchone()[0],
            "confirmed_faces": conn.execute("SELECT COUNT(*) FROM faces WHERE is_confirmed=1").fetchone()[0],
            "unassigned_faces": conn.execute(
                "SELECT COUNT(*) FROM faces WHERE person_id IS NULL AND is_ignored=0"
            ).fetchone()[0],
            "duplicate_groups": conn.execute("SELECT COUNT(*) FROM duplicate_groups").fetchone()[0],
        }

    # ── Audit ────────────────────────────────────────────────────────────────

    def log(self, action: str, photo_id: int = None, face_id: int = None,
            person_id: int = None, details: str = None):
        conn = self._conn()
        conn.execute(
            "INSERT INTO audit_log (action, photo_id, face_id, person_id, details) VALUES (?,?,?,?,?)",
            (action, photo_id, face_id, person_id, details),
        )
        conn.commit()


def _adaptive_threshold(confirmed_count: int) -> float:
    """Return match distance threshold based on how many confirmed faces exist.

    Fewer confirmed samples → looser threshold (catch more candidates).
    More confirmed samples  → tighter threshold (higher precision).
    """
    if confirmed_count < 3:
        return 0.65
    elif confirmed_count < 8:
        return 0.60
    elif confirmed_count < 20:
        return 0.55
    elif confirmed_count < 50:
        return 0.50
    else:
        return 0.45
