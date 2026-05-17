"""Round 1: DB core paths, Scanner basics, UI signal handlers."""

import os
import sys
import tempfile
import shutil
import threading
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core.face_engine import encode_embedding
from core.database import Database, _adaptive_threshold

PASS = []
FAIL = []

def ok(name):
    PASS.append(name)
    print(f"  ✓ {name}")

def fail(name, err):
    FAIL.append(name)
    print(f"  ✗ {name}: {err}")

def make_db():
    tmp = tempfile.mkdtemp()
    db = Database(os.path.join(tmp, "test.db"))
    return db, tmp

def make_emb(group_id, noise=0.0, seed=None):
    base = np.random.default_rng(group_id * 12345 + 1).normal(0, 1, 128).astype(np.float32)
    base /= np.linalg.norm(base)
    if noise > 0 and seed is not None:
        delta = np.random.default_rng(seed).normal(0, noise, 128).astype(np.float32)
        base = base + delta
        base /= np.linalg.norm(base)
    return base


# ── Round 1A: DB core paths ────────────────────────────────────────────────────
print("=== ROUND 1A: DB core paths ===")

def test_upsert_and_get():
    db, tmp = make_db()
    try:
        pid = db.upsert_photo({"file_path": "/p/a.jpg", "file_name": "a.jpg", "sha256_hash": "aaa"})
        assert pid > 0
        row = db.get_photo(pid)
        assert row["file_path"] == "/p/a.jpg"
        ok("upsert_and_get_photo")
    except Exception as e:
        fail("upsert_and_get", e)
    finally:
        shutil.rmtree(tmp)

def test_upsert_idempotent():
    db, tmp = make_db()
    try:
        pid1 = db.upsert_photo({"file_path": "/p/b.jpg", "file_name": "b.jpg"})
        pid2 = db.upsert_photo({"file_path": "/p/b.jpg", "file_name": "b.jpg", "sha256_hash": "new"})
        # Same file_path → same row (ON CONFLICT UPDATE)
        assert db.count_photos() == 1
        row = db.get_photo_by_path("/p/b.jpg")
        assert row["sha256_hash"] == "new"
        ok("upsert_idempotent_updates")
    except Exception as e:
        fail("upsert_idempotent", e)
    finally:
        shutil.rmtree(tmp)

def test_create_and_get_person():
    db, tmp = make_db()
    try:
        pid = db.create_person("Alice", relationship="friend")
        row = db.get_person(pid)
        assert row["name"] == "Alice"
        assert row["relationship"] == "friend"
        ok("create_and_get_person")
    except Exception as e:
        fail("create_and_get_person", e)
    finally:
        shutil.rmtree(tmp)

def test_update_person():
    db, tmp = make_db()
    try:
        pid = db.create_person("Bob")
        db.update_person(pid, name="Robert", notes="updated")
        row = db.get_person(pid)
        assert row["name"] == "Robert"
        assert row["notes"] == "updated"
        ok("update_person")
    except Exception as e:
        fail("update_person", e)
    finally:
        shutil.rmtree(tmp)

def test_insert_and_confirm_face():
    db, tmp = make_db()
    try:
        photo_id = db.upsert_photo({"file_path": "/p/c.jpg", "file_name": "c.jpg"})
        pid = db.create_person("Carol")
        fid = db.insert_face({
            "photo_id": photo_id,
            "bbox_top": 10, "bbox_right": 60, "bbox_bottom": 60, "bbox_left": 10,
            "embedding": encode_embedding(make_emb(0)),
        })
        db.confirm_face(fid, pid)
        person = db.get_person(pid)
        assert person["confirmed_count"] == 1
        ok("insert_and_confirm_face")
    except Exception as e:
        fail("insert_and_confirm_face", e)
    finally:
        shutil.rmtree(tmp)

def test_reject_face():
    db, tmp = make_db()
    try:
        photo_id = db.upsert_photo({"file_path": "/p/d.jpg", "file_name": "d.jpg"})
        pid = db.create_person("Dave")
        fid = db.insert_face({
            "photo_id": photo_id,
            "bbox_top": 0, "bbox_right": 50, "bbox_bottom": 50, "bbox_left": 0,
        })
        db.confirm_face(fid, pid)
        db.reject_face(fid, pid)
        person = db.get_person(pid)
        assert person["confirmed_count"] == 0
        ok("reject_face_decrements_count")
    except Exception as e:
        fail("reject_face", e)
    finally:
        shutil.rmtree(tmp)

def test_ignore_face():
    db, tmp = make_db()
    try:
        photo_id = db.upsert_photo({"file_path": "/p/e.jpg", "file_name": "e.jpg"})
        pid = db.create_person("Eve")
        fid = db.insert_face({
            "photo_id": photo_id,
            "bbox_top": 0, "bbox_right": 50, "bbox_bottom": 50, "bbox_left": 0,
        })
        db.confirm_face(fid, pid)
        db.ignore_face(fid)
        person = db.get_person(pid)
        assert person["confirmed_count"] == 0
        unassigned = db.get_unassigned_faces()
        assert all(f["id"] != fid for f in unassigned)
        ok("ignore_face")
    except Exception as e:
        fail("ignore_face", e)
    finally:
        shutil.rmtree(tmp)

def test_merge_preserves_confirmed():
    db, tmp = make_db()
    try:
        photo_id = db.upsert_photo({"file_path": "/p/f.jpg", "file_name": "f.jpg"})
        pid1 = db.create_person("Source")
        pid2 = db.create_person("Target")
        fid = db.insert_face({
            "photo_id": photo_id,
            "bbox_top": 0, "bbox_right": 50, "bbox_bottom": 50, "bbox_left": 0,
            "embedding": encode_embedding(make_emb(1)),
        })
        db.confirm_face(fid, pid1)
        db.merge_people(pid1, pid2)
        person2 = db.get_person(pid2)
        assert person2["confirmed_count"] == 1, f"expected 1 after merge, got {person2['confirmed_count']}"
        # Source person should be deleted
        assert db.get_person(pid1) is None
        ok("merge_preserves_confirmed")
    except Exception as e:
        fail("merge_preserves_confirmed", e)
    finally:
        shutil.rmtree(tmp)

def test_scan_session_lifecycle():
    db, tmp = make_db()
    try:
        sid = db.start_scan_session(["/a", "/b"])
        row = db.get_last_scan_session()
        assert row["status"] == "running"
        db.finish_scan_session(sid, {"photos_found": 10, "new_photos": 5, "updated_photos": 2,
                                      "missing_photos": 0, "faces_detected": 0})
        row = db.get_last_scan_session()
        assert row["status"] == "completed"
        assert row["photos_found"] == 10
        ok("scan_session_lifecycle")
    except Exception as e:
        fail("scan_session_lifecycle", e)
    finally:
        shutil.rmtree(tmp)

def test_get_all_people_ordering():
    db, tmp = make_db()
    try:
        # People should be ordered by confirmed_count DESC
        p1 = db.create_person("Low")
        p2 = db.create_person("High")
        photo_id = db.upsert_photo({"file_path": "/p/g.jpg", "file_name": "g.jpg"})
        for _ in range(5):
            fid = db.insert_face({
                "photo_id": photo_id,
                "bbox_top": 0, "bbox_right": 50, "bbox_bottom": 50, "bbox_left": 0,
                "embedding": encode_embedding(make_emb(2)),
            })
            db.confirm_face(fid, p2)
        people = db.get_all_people()
        assert people[0]["id"] == p2, "highest count person should be first"
        ok("get_all_people_ordering")
    except Exception as e:
        fail("get_all_people_ordering", e)
    finally:
        shutil.rmtree(tmp)

def test_adaptive_threshold_boundary():
    try:
        # Boundaries: <3 → 0.65, 3-7 → 0.60, 8-19 → 0.55, 20-49 → 0.50, ≥50 → 0.45
        cases = [(0, 0.65), (2, 0.65), (3, 0.60), (8, 0.55), (20, 0.50), (50, 0.45)]
        for n, expected in cases:
            got = _adaptive_threshold(n)
            assert got == expected, f"threshold({n}) = {got}, expected {expected}"
        ok("adaptive_threshold_boundaries")
    except AssertionError as e:
        fail("adaptive_threshold_boundary", e)

test_upsert_and_get()
test_upsert_idempotent()
test_create_and_get_person()
test_update_person()
test_insert_and_confirm_face()
test_reject_face()
test_ignore_face()
test_merge_preserves_confirmed()
test_scan_session_lifecycle()
test_get_all_people_ordering()
test_adaptive_threshold_boundary()


# ── Round 1B: Scanner basics ──────────────────────────────────────────────────
print("\n=== ROUND 1B: Scanner basics ===")

def test_scanner_finds_jpegs():
    from core.scanner import ScanWorker
    tmp = tempfile.mkdtemp()
    try:
        jpeg_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"
        for i in range(4):
            with open(os.path.join(tmp, f"img{i}.jpg"), "wb") as f:
                f.write(jpeg_bytes)
        # Non-photo file should be ignored
        with open(os.path.join(tmp, "notes.txt"), "w") as f:
            f.write("not a photo")

        db = Database(os.path.join(tmp, "db", "test.db"))
        ev = threading.Event()
        results = {}
        ScanWorker(
            db=db, folders=[tmp], thumb_dir=os.path.join(tmp, "thumbs"),
            on_progress=lambda *a: None,
            on_finished=lambda s: (results.update(s), ev.set()),
            on_error=lambda e: None,
        ).start()
        ev.wait(timeout=30)
        assert results.get("photos_found") == 4, f"expected 4, got {results.get('photos_found')}"
        ok("scanner_finds_4_jpegs_ignores_txt")
    except Exception as e:
        fail("scanner_finds_jpegs", e)
    finally:
        shutil.rmtree(tmp)

def test_scanner_marks_missing():
    from core.scanner import ScanWorker
    tmp = tempfile.mkdtemp()
    try:
        jpeg_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"
        p = os.path.join(tmp, "will_delete.jpg")
        with open(p, "wb") as f:
            f.write(jpeg_bytes)

        db = Database(os.path.join(tmp, "db", "test.db"))
        ev = threading.Event()
        ScanWorker(
            db=db, folders=[tmp], thumb_dir=os.path.join(tmp, "thumbs"),
            on_progress=lambda *a: None,
            on_finished=lambda s: ev.set(),
            on_error=lambda e: None,
        ).start()
        ev.wait(timeout=30)
        assert db.count_photos() == 1

        # Delete file and re-scan — should be marked missing
        os.remove(p)
        ev2 = threading.Event()
        ScanWorker(
            db=db, folders=[tmp], thumb_dir=os.path.join(tmp, "thumbs"),
            on_progress=lambda *a: None,
            on_finished=lambda s: ev2.set(),
            on_error=lambda e: None,
        ).start()
        ev2.wait(timeout=30)
        # count_photos excludes missing
        assert db.count_photos() == 0, f"missing file should be excluded from count"
        stats = db.get_stats()
        assert stats["missing_photos"] == 1
        ok("scanner_marks_missing_files")
    except Exception as e:
        fail("scanner_marks_missing", e)
    finally:
        shutil.rmtree(tmp)

def test_scanner_empty_folder():
    from core.scanner import ScanWorker
    tmp = tempfile.mkdtemp()
    try:
        db = Database(os.path.join(tmp, "db", "test.db"))
        ev = threading.Event()
        results = {}
        ScanWorker(
            db=db, folders=[tmp], thumb_dir=os.path.join(tmp, "thumbs"),
            on_progress=lambda *a: None,
            on_finished=lambda s: (results.update(s), ev.set()),
            on_error=lambda e: None,
        ).start()
        ev.wait(timeout=15)
        assert results.get("photos_found", 0) == 0
        ok("scanner_empty_folder_no_crash")
    except Exception as e:
        fail("scanner_empty_folder", e)
    finally:
        shutil.rmtree(tmp)

def test_scanner_nonexistent_folder():
    from core.scanner import ScanWorker
    tmp = tempfile.mkdtemp()
    try:
        db = Database(os.path.join(tmp, "db", "test.db"))
        ev = threading.Event()
        errors = []
        ScanWorker(
            db=db, folders=["/this/path/does/not/exist/xyz123"],
            thumb_dir=os.path.join(tmp, "thumbs"),
            on_progress=lambda *a: None,
            on_finished=lambda s: ev.set(),
            on_error=lambda e: (errors.append(e), ev.set()),
        ).start()
        ev.wait(timeout=15)
        # Should complete (finish or error) without hanging
        assert ev.is_set(), "worker should finish even for nonexistent folder"
        ok("scanner_nonexistent_folder_no_hang")
    except Exception as e:
        fail("scanner_nonexistent_folder", e)
    finally:
        shutil.rmtree(tmp)

test_scanner_finds_jpegs()
test_scanner_marks_missing()
test_scanner_empty_folder()
test_scanner_nonexistent_folder()


# ── Round 1C: UI signal handlers ─────────────────────────────────────────────
print("\n=== ROUND 1C: UI signal handlers ===")

def setup_qt_mocks():
    from PyQt6.QtWidgets import QMessageBox, QApplication
    app = QApplication.instance() or QApplication(sys.argv)
    # Mock all blocking dialogs
    QMessageBox.information = staticmethod(lambda *a, **kw: None)
    QMessageBox.warning = staticmethod(lambda *a, **kw: None)
    QMessageBox.critical = staticmethod(lambda *a, **kw: None)
    QMessageBox.question = staticmethod(lambda *a, **kw: QMessageBox.StandardButton.Yes)
    return app

def test_scan_view_no_folders_log():
    try:
        app = setup_qt_mocks()
        from ui.scan_view import ScanView
        db, tmp = make_db()
        try:
            sv = ScanView(db=db, thumb_dir=tmp)
            sv.set_folders([])
            sv._start_scan()  # no folders → logs message, does NOT start worker
            assert sv._worker is None
            ok("scan_view_no_folders_no_crash")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("scan_view_no_folders_log", e)

def test_scan_view_stop_no_worker():
    try:
        app = setup_qt_mocks()
        from ui.scan_view import ScanView
        db, tmp = make_db()
        try:
            sv = ScanView(db=db, thumb_dir=tmp)
            sv._stop_scan()  # no worker — must not raise
            ok("scan_view_stop_no_worker_no_crash")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("scan_view_stop_no_worker", e)

def test_scan_view_refresh_stats():
    try:
        app = setup_qt_mocks()
        from ui.scan_view import ScanView
        db, tmp = make_db()
        try:
            sv = ScanView(db=db, thumb_dir=tmp)
            sv.refresh_stats()  # must not raise even with empty DB
            ok("scan_view_refresh_stats_empty_db")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("scan_view_refresh_stats", e)

def test_people_view_no_crash_empty_db():
    try:
        app = setup_qt_mocks()
        from ui.people_view import PeopleView
        from core.face_engine import FaceEngine
        db, tmp = make_db()
        try:
            fe = FaceEngine(db=db, thumb_dir=tmp)
            pv = PeopleView(db=db, face_engine=fe)
            pv.refresh()  # empty DB — must not crash
            ok("people_view_refresh_empty_db")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("people_view_no_crash_empty_db", e)

def test_people_view_with_people():
    try:
        app = setup_qt_mocks()
        from ui.people_view import PeopleView
        from core.face_engine import FaceEngine
        db, tmp = make_db()
        try:
            fe = FaceEngine(db=db, thumb_dir=tmp)
            pid = db.create_person("TestRefresh")
            photo_id = db.upsert_photo({"file_path": "/p/refresh.jpg", "file_name": "refresh.jpg"})
            fid = db.insert_face({
                "photo_id": photo_id,
                "bbox_top": 0, "bbox_right": 50, "bbox_bottom": 50, "bbox_left": 0,
                "embedding": encode_embedding(make_emb(20)),
            })
            db.confirm_face(fid, pid)
            pv = PeopleView(db=db, face_engine=fe)
            pv.refresh()
            ok("people_view_refresh_with_person")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("people_view_with_people", e)

test_scan_view_no_folders_log()
test_scan_view_stop_no_worker()
test_scan_view_refresh_stats()
test_people_view_no_crash_empty_db()
test_people_view_with_people()


# ── Summary ────────────────────────────────────────────────────────────────────
print(f"\nRound 1 Results: {len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    print("FAILURES:", FAIL)
    sys.exit(1)
else:
    print("ALL PASSED")
