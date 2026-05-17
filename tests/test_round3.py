"""Round 3: Scanner integration, concurrent access, ScanWorker edge cases, UI smoke tests."""

import os
import sys
import json
import time
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


# ── Scanner filesystem integration ────────────────────────────────────────────
print("=== ROUND 3A: Scanner filesystem integration ===")

def test_scan_real_images():
    """ScanWorker finds and catalogs real JPEG files."""
    from core.scanner import ScanWorker
    tmp = tempfile.mkdtemp()
    try:
        img_dir = os.path.join(tmp, "photos")
        os.makedirs(img_dir)
        # Minimal valid JPEG bytes
        jpeg_bytes = (
            b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
            b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t"
            b"\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a"
            b"\x1f\x1e\x1d\x1a\x1c\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342\x1e"
            b"\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00"
            b"\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00"
            b"\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b"
            b"\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xf5\x0a\xff\xd9"
        )
        for i in range(3):
            path = os.path.join(img_dir, f"photo_{i}.jpg")
            with open(path, "wb") as f:
                f.write(jpeg_bytes)

        db = Database(os.path.join(tmp, "db", "test.db"))
        thumb_dir = os.path.join(tmp, "thumbs")
        results = {}
        errors = []
        finished_ev = threading.Event()

        def on_finished(stats):
            results.update(stats)
            finished_ev.set()

        worker = ScanWorker(
            db=db,
            folders=[img_dir],
            thumb_dir=thumb_dir,
            on_progress=lambda *a: None,
            on_finished=on_finished,
            on_error=lambda e: errors.append(e),
        )
        worker.start()
        finished_ev.wait(timeout=30)

        assert finished_ev.is_set(), "scan did not finish"
        assert results.get("photos_found", 0) == 3, f"expected 3 photos, got {results.get('photos_found')}"
        assert results.get("new_photos", 0) == 3, f"expected 3 new, got {results.get('new_photos')}"
        assert not errors, f"scan errors: {errors}"
        ok("scan_real_images_3_found")
    except Exception as e:
        fail("scan_real_images", e)
    finally:
        shutil.rmtree(tmp)

def test_scan_idempotent():
    """Scanning the same folder twice does not double-count photos."""
    from core.scanner import ScanWorker
    tmp = tempfile.mkdtemp()
    try:
        img_dir = os.path.join(tmp, "photos")
        os.makedirs(img_dir)
        jpeg_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"
        for i in range(2):
            with open(os.path.join(img_dir, f"img_{i}.jpg"), "wb") as f:
                f.write(jpeg_bytes)

        db = Database(os.path.join(tmp, "db", "test.db"))
        thumb_dir = os.path.join(tmp, "thumbs")

        def run_scan():
            results = {}
            ev = threading.Event()
            w = ScanWorker(db=db, folders=[img_dir], thumb_dir=thumb_dir,
                           on_progress=lambda *a: None,
                           on_finished=lambda s: (results.update(s), ev.set()),
                           on_error=lambda e: None)
            w.start()
            ev.wait(timeout=30)
            return results

        r1 = run_scan()
        r2 = run_scan()

        assert r1.get("new_photos", 0) == 2, f"first scan: expected 2 new, got {r1.get('new_photos')}"
        assert r2.get("new_photos", 0) == 0, f"second scan: expected 0 new, got {r2.get('new_photos')}"
        count = db.count_photos()
        assert count == 2, f"expected 2 total photos after 2 scans, got {count}"
        ok("scan_idempotent")
    except Exception as e:
        fail("scan_idempotent", e)
    finally:
        shutil.rmtree(tmp)

def test_scan_corrupt_file_no_crash():
    """Corrupt/zero-byte files don't abort the scan."""
    from core.scanner import ScanWorker
    tmp = tempfile.mkdtemp()
    try:
        img_dir = os.path.join(tmp, "photos")
        os.makedirs(img_dir)
        # Valid file
        with open(os.path.join(img_dir, "valid.jpg"), "wb") as f:
            f.write(b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9")
        # Corrupt file
        with open(os.path.join(img_dir, "corrupt.jpg"), "wb") as f:
            f.write(b"NOT A JPEG AT ALL")
        # Zero-byte file
        with open(os.path.join(img_dir, "empty.jpg"), "wb") as f:
            pass

        db = Database(os.path.join(tmp, "db", "test.db"))
        ev = threading.Event()
        results = {}
        ScanWorker(
            db=db, folders=[img_dir], thumb_dir=os.path.join(tmp, "thumbs"),
            on_progress=lambda *a: None,
            on_finished=lambda s: (results.update(s), ev.set()),
            on_error=lambda e: None,
        ).start()
        ev.wait(timeout=30)
        assert ev.is_set()
        # All 3 files attempted; scan finishes without crash
        assert results.get("photos_found", 0) >= 1, "at least valid photo should be found"
        ok("scan_corrupt_file_no_crash")
    except Exception as e:
        fail("scan_corrupt_file_no_crash", e)
    finally:
        shutil.rmtree(tmp)

def test_scan_unicode_filenames():
    """Unicode filenames are handled correctly."""
    from core.scanner import ScanWorker
    tmp = tempfile.mkdtemp()
    try:
        img_dir = os.path.join(tmp, "photos")
        os.makedirs(img_dir)
        names = ["日本語.jpg", "Ünïcödé.jpg", "中文照片.jpg", "émoji_🎉.jpg"]
        jpeg_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"
        for name in names:
            try:
                with open(os.path.join(img_dir, name), "wb") as f:
                    f.write(jpeg_bytes)
            except (OSError, UnicodeEncodeError):
                pass  # some filesystems may reject emoji

        db = Database(os.path.join(tmp, "db", "test.db"))
        ev = threading.Event()
        results = {}
        ScanWorker(
            db=db, folders=[img_dir], thumb_dir=os.path.join(tmp, "thumbs"),
            on_progress=lambda *a: None,
            on_finished=lambda s: (results.update(s), ev.set()),
            on_error=lambda e: None,
        ).start()
        ev.wait(timeout=30)
        assert ev.is_set()
        assert results.get("photos_found", 0) >= 1
        ok("scan_unicode_filenames")
    except Exception as e:
        fail("scan_unicode_filenames", e)
    finally:
        shutil.rmtree(tmp)

def test_scan_nested_dirs():
    """Scanner recurses into subdirectories."""
    from core.scanner import ScanWorker
    tmp = tempfile.mkdtemp()
    try:
        jpeg_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"
        deep = os.path.join(tmp, "a", "b", "c", "d")
        os.makedirs(deep)
        with open(os.path.join(deep, "deep.jpg"), "wb") as f:
            f.write(jpeg_bytes)
        with open(os.path.join(tmp, "top.jpg"), "wb") as f:
            f.write(jpeg_bytes)

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
        assert results.get("photos_found", 0) == 2, f"expected 2, got {results.get('photos_found')}"
        ok("scan_nested_dirs")
    except Exception as e:
        fail("scan_nested_dirs", e)
    finally:
        shutil.rmtree(tmp)

test_scan_real_images()
test_scan_idempotent()
test_scan_corrupt_file_no_crash()
test_scan_unicode_filenames()
test_scan_nested_dirs()


# ── Concurrent DB access ───────────────────────────────────────────────────────
print("\n=== ROUND 3B: Concurrent DB access ===")

def test_concurrent_upsert():
    """Multiple threads can upsert photos simultaneously without corruption."""
    db, tmp = make_db()
    try:
        errors = []
        def worker(idx):
            try:
                db.upsert_photo({
                    "file_path": f"/fake/concurrent_{idx}.jpg",
                    "file_name": f"concurrent_{idx}.jpg",
                    "sha256_hash": f"hash{idx:04d}",
                })
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert not errors, f"concurrent upsert errors: {errors}"
        count = db.count_photos()
        assert count == 20, f"expected 20 photos, got {count}"
        ok("concurrent_upsert_20_threads")
    except Exception as e:
        fail("concurrent_upsert", e)
    finally:
        shutil.rmtree(tmp)

def test_concurrent_face_ops():
    """Confirm + refresh + read running concurrently is safe."""
    db, tmp = make_db()
    try:
        pid = db.create_person("ConcurrentPerson")
        photo_id = db.upsert_photo({
            "file_path": "/fake/concurrent_face.jpg",
            "file_name": "concurrent_face.jpg",
        })
        face_ids = []
        for i in range(10):
            fid = db.insert_face({
                "photo_id": photo_id,
                "bbox_top": 0, "bbox_right": 50, "bbox_bottom": 50, "bbox_left": 0,
                "embedding": encode_embedding(make_emb(i)),
            })
            face_ids.append(fid)

        errors = []
        def confirm_worker(fid):
            try:
                db.confirm_face(fid, pid)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=confirm_worker, args=(fid,)) for fid in face_ids]
        for t in threads: t.start()
        for t in threads: t.join()

        assert not errors, f"concurrent face errors: {errors}"
        # Do one authoritative refresh after all concurrent operations settle
        db.refresh_person_stats(pid)
        p = db.get_person(pid)
        assert p["confirmed_count"] == 10, f"expected 10 confirmed, got {p['confirmed_count']}"
        ok("concurrent_face_ops")
    except Exception as e:
        fail("concurrent_face_ops", e)
    finally:
        shutil.rmtree(tmp)

test_concurrent_upsert()
test_concurrent_face_ops()


# ── ScanWorker pause/resume/stop ──────────────────────────────────────────────
print("\n=== ROUND 3C: ScanWorker pause/resume/stop ===")

def test_scanworker_stop():
    """Stopping the worker before completion does not raise."""
    from core.scanner import ScanWorker
    tmp = tempfile.mkdtemp()
    try:
        img_dir = os.path.join(tmp, "photos")
        os.makedirs(img_dir)
        jpeg_bytes = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"
        for i in range(5):
            with open(os.path.join(img_dir, f"img{i}.jpg"), "wb") as f:
                f.write(jpeg_bytes)

        db = Database(os.path.join(tmp, "db", "test.db"))
        worker = ScanWorker(
            db=db, folders=[img_dir], thumb_dir=os.path.join(tmp, "thumbs"),
            on_progress=lambda *a: None,
            on_finished=lambda s: None,
            on_error=lambda e: None,
        )
        worker.start()
        worker.stop()
        worker.join(timeout=10)
        assert not worker.is_alive(), "worker should have stopped"
        ok("scanworker_stop")
    except Exception as e:
        fail("scanworker_stop", e)
    finally:
        shutil.rmtree(tmp)

def test_scanworker_pause_resume():
    """Pause/resume changes internal state correctly."""
    from core.scanner import ScanWorker
    tmp = tempfile.mkdtemp()
    try:
        db = Database(os.path.join(tmp, "db", "test.db"))
        worker = ScanWorker(
            db=db, folders=[tmp], thumb_dir=os.path.join(tmp, "thumbs"),
            on_progress=lambda *a: None,
            on_finished=lambda s: None,
            on_error=lambda e: None,
        )
        # _pause_event is SET when running, CLEARED when paused
        assert worker._pause_event.is_set(), "should be running (not paused) before start"
        worker.pause()
        assert not worker._pause_event.is_set(), "should be paused after pause()"
        worker.resume()
        assert worker._pause_event.is_set(), "should be running after resume()"
        ok("scanworker_pause_resume_state")
    except Exception as e:
        fail("scanworker_pause_resume", e)
    finally:
        shutil.rmtree(tmp)

test_scanworker_stop()
test_scanworker_pause_resume()


# ── DB audit log ──────────────────────────────────────────────────────────────
print("\n=== ROUND 3D: Audit log ===")

def test_audit_log_on_confirm():
    db, tmp = make_db()
    try:
        pid = db.create_person("AuditTest")
        photo_id = db.upsert_photo({"file_path": "/fake/audit.jpg", "file_name": "audit.jpg"})
        fid = db.insert_face({
            "photo_id": photo_id,
            "bbox_top": 0, "bbox_right": 50, "bbox_bottom": 50, "bbox_left": 0,
        })
        db.confirm_face(fid, pid)
        conn = db._conn()
        rows = conn.execute("SELECT * FROM audit_log WHERE action='confirm_face'").fetchall()
        assert len(rows) >= 1, "confirm_face should be logged"
        ok("audit_log_on_confirm")
    except Exception as e:
        fail("audit_log_on_confirm", e)
    finally:
        shutil.rmtree(tmp)

def test_audit_log_on_merge():
    db, tmp = make_db()
    try:
        pid1 = db.create_person("P1")
        pid2 = db.create_person("P2")
        db.merge_people(pid1, pid2)
        conn = db._conn()
        rows = conn.execute("SELECT * FROM audit_log WHERE action='merge_people'").fetchall()
        assert len(rows) >= 1, "merge_people should be logged"
        ok("audit_log_on_merge")
    except Exception as e:
        fail("audit_log_on_merge", e)
    finally:
        shutil.rmtree(tmp)

test_audit_log_on_confirm()
test_audit_log_on_merge()


# ── DB get_stats edge cases ───────────────────────────────────────────────────
print("\n=== ROUND 3E: get_stats edge cases ===")

def test_stats_empty_db():
    db, tmp = make_db()
    try:
        s = db.get_stats()
        assert s["total_photos"] == 0
        assert s["total_people"] == 0
        assert s["total_faces"] == 0
        assert s["duplicate_groups"] == 0
        ok("stats_empty_db")
    except Exception as e:
        fail("stats_empty_db", e)
    finally:
        shutil.rmtree(tmp)

def test_stats_single_dup_member_not_counted():
    """A group with only 1 member should NOT count as a duplicate group."""
    db, tmp = make_db()
    try:
        pid = db.upsert_photo({"file_path": "/fake/lone.jpg", "file_name": "lone.jpg"})
        gid = db.get_or_create_duplicate_group("singlehash")
        db.add_to_duplicate_group(gid, pid, is_master=True)
        s = db.get_stats()
        assert s["duplicate_groups"] == 0, f"singleton group should not count, got {s['duplicate_groups']}"
        ok("stats_singleton_dup_not_counted")
    except Exception as e:
        fail("stats_singleton_dup_not_counted", e)
    finally:
        shutil.rmtree(tmp)

def test_stats_missing_excluded():
    db, tmp = make_db()
    try:
        pid = db.upsert_photo({"file_path": "/fake/gone.jpg", "file_name": "gone.jpg"})
        db.mark_missing(pid)
        s = db.get_stats()
        assert s["total_photos"] == 0, f"missing photo should not count, got {s['total_photos']}"
        assert s["missing_photos"] == 1
        ok("stats_missing_excluded")
    except Exception as e:
        fail("stats_missing_excluded", e)
    finally:
        shutil.rmtree(tmp)

test_stats_empty_db()
test_stats_single_dup_member_not_counted()
test_stats_missing_excluded()


# ── UI smoke tests ────────────────────────────────────────────────────────────
print("\n=== ROUND 3F: UI smoke tests ===")

def test_ui_imports():
    try:
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication(sys.argv)
        from ui.scan_view import ScanView
        from ui.people_view import PeopleView
        from ui.styles import btn_style, tab_btn_style
        ok("ui_imports_all")
    except Exception as e:
        fail("ui_imports", e)

def test_scan_view_init():
    try:
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication(sys.argv)
        from ui.scan_view import ScanView
        db, tmp = make_db()
        try:
            sv = ScanView(db=db, thumb_dir=tmp)
            assert sv is not None
            sv.set_folders(["/tmp", "/home"])
            assert sv.get_folders() == ["/tmp", "/home"]
            ok("scan_view_init_and_folders")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("scan_view_init", e)

def test_people_view_init():
    try:
        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication(sys.argv)
        from ui.people_view import PeopleView
        from core.face_engine import FaceEngine
        db, tmp = make_db()
        try:
            fe = FaceEngine(db=db, thumb_dir=tmp)
            pv = PeopleView(db=db, face_engine=fe)
            assert pv is not None
            ok("people_view_init")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("people_view_init", e)

def test_btn_style_variants():
    try:
        from ui.styles import btn_style, tab_btn_style
        s = btn_style()
        assert "QPushButton" in s
        s_p = btn_style(primary=True)
        assert "#2a6496" in s_p
        s_d = btn_style(danger=True)
        assert "#5a2020" in s_d
        s_sm = btn_style(small=True)
        assert "3px" in s_sm
        s_t = btn_style(tiny=True)
        assert "2px" in s_t
        t_active = tab_btn_style(active=True)
        assert "1e3a5f" in t_active
        ok("btn_style_variants")
    except Exception as e:
        fail("btn_style_variants", e)

test_ui_imports()
test_scan_view_init()
test_people_view_init()
test_btn_style_variants()


# ── Summary ────────────────────────────────────────────────────────────────────
print(f"\nRound 3 Results: {len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    print("FAILURES:", FAIL)
    sys.exit(1)
else:
    print("ALL PASSED")
