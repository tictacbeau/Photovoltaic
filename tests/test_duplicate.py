"""Tests for Stage 3a: Duplicate Manager — DB methods + UI."""
import os
import sys
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core.database import Database

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


def upsert(db, path, sha=None, w=None, h=None, size=None):
    return db.upsert_photo({
        "file_path": path,
        "file_name": os.path.basename(path),
        "sha256_hash": sha or ("hash_" + os.path.basename(path)),
        "width": w,
        "height": h,
        "file_size": size,
    })


def setup_qt():
    from PyQt6.QtWidgets import QApplication, QMessageBox
    app = QApplication.instance() or QApplication(sys.argv)
    QMessageBox.information = staticmethod(lambda *a, **kw: None)
    QMessageBox.warning = staticmethod(lambda *a, **kw: None)
    QMessageBox.critical = staticmethod(lambda *a, **kw: None)
    QMessageBox.question = staticmethod(
        lambda *a, **kw: __import__("PyQt6.QtWidgets", fromlist=["QMessageBox"]).QMessageBox.StandardButton.Yes
    )
    return app


def make_dup_group(db, paths):
    """Create a duplicate group and return (group_id, [photo_ids])."""
    group_hash = "testhash_" + paths[0]
    gid = db.get_or_create_duplicate_group(group_hash)
    ids = []
    for p in paths:
        pid = upsert(db, p)
        db.add_to_duplicate_group(gid, pid)
        ids.append(pid)
    return gid, ids


# ── A: DB duplicate methods ───────────────────────────────────────────────────

print("=== A: DB Duplicate Methods ===")


def test_get_duplicate_groups_empty():
    try:
        db, tmp = make_db()
        try:
            groups = db.get_duplicate_groups()
            assert groups == []
            ok("get_duplicate_groups_empty")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("get_duplicate_groups_empty", e)


def test_get_duplicate_groups_only_multi():
    try:
        db, tmp = make_db()
        try:
            # Group with 2 members (should appear)
            gid2, _ = make_dup_group(db, ["/a/img1.jpg", "/a/img2.jpg"])
            # Group with 1 member (should NOT appear — not a duplicate)
            gid1, _ = make_dup_group(db, ["/a/img3.jpg"])
            # Remove one member to leave only 1
            # Actually make_dup_group adds both; let's make a single-member group manually
            gid_solo = db.get_or_create_duplicate_group("solo_hash")
            solo_id = upsert(db, "/a/solo.jpg")
            db.add_to_duplicate_group(gid_solo, solo_id)

            groups = db.get_duplicate_groups()
            ids = [g["id"] for g in groups]
            assert gid2 in ids
            assert gid_solo not in ids
            ok("get_duplicate_groups_only_multi")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("get_duplicate_groups_only_multi", e)


def test_get_duplicate_group_photos():
    try:
        db, tmp = make_db()
        try:
            gid, pids = make_dup_group(db, ["/a/img1.jpg", "/a/img2.jpg", "/a/img3.jpg"])
            photos = db.get_duplicate_group_photos(gid)
            assert len(photos) == 3
            found_ids = {p["id"] for p in photos}
            assert found_ids == set(pids)
            ok("get_duplicate_group_photos")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("get_duplicate_group_photos", e)


def test_set_duplicate_master():
    try:
        db, tmp = make_db()
        try:
            gid, pids = make_dup_group(db, ["/a/img1.jpg", "/a/img2.jpg"])
            db.set_duplicate_master(gid, pids[0])
            photos = db.get_duplicate_group_photos(gid)
            master = [p for p in photos if p["is_master"]]
            assert len(master) == 1
            assert master[0]["id"] == pids[0]
            # Change master
            db.set_duplicate_master(gid, pids[1])
            photos = db.get_duplicate_group_photos(gid)
            master = [p for p in photos if p["is_master"]]
            assert len(master) == 1
            assert master[0]["id"] == pids[1]
            ok("set_duplicate_master")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("set_duplicate_master", e)


def test_dismiss_duplicate_group():
    try:
        db, tmp = make_db()
        try:
            gid, pids = make_dup_group(db, ["/a/img1.jpg", "/a/img2.jpg"])
            assert len(db.get_duplicate_groups()) == 1
            db.dismiss_duplicate_group(gid)
            assert len(db.get_duplicate_groups()) == 0
            # Photos still exist
            for pid in pids:
                assert db.get_photo(pid) is not None
            ok("dismiss_duplicate_group")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("dismiss_duplicate_group", e)


def test_delete_photo_removes_record():
    try:
        db, tmp = make_db()
        try:
            pid = upsert(db, "/a/img.jpg")
            assert db.get_photo(pid) is not None
            result = db.delete_photo(pid)
            assert result is True
            assert db.get_photo(pid) is None
            ok("delete_photo_removes_record")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("delete_photo_removes_record", e)


def test_delete_photo_cleans_dup_membership():
    try:
        db, tmp = make_db()
        try:
            gid, pids = make_dup_group(db, ["/a/img1.jpg", "/a/img2.jpg"])
            db.delete_photo(pids[0])
            # Group now has only 1 member → won't show in get_duplicate_groups
            photos = db.get_duplicate_group_photos(gid)
            assert len(photos) == 1
            assert photos[0]["id"] == pids[1]
            ok("delete_photo_cleans_dup_membership")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("delete_photo_cleans_dup_membership", e)


def test_delete_photo_cleans_faces():
    try:
        db, tmp = make_db()
        try:
            pid = upsert(db, "/a/img.jpg")
            person_id = db.create_person("Test Person")
            db.insert_face({
                "photo_id": pid, "bbox_top": 10, "bbox_left": 10,
                "bbox_bottom": 60, "bbox_right": 60,
            })
            faces_before = db.get_faces_for_photo(pid)
            assert len(faces_before) > 0
            db.delete_photo(pid)
            # Face record should be gone — check via raw query
            conn = db._conn()
            faces_after = conn.execute("SELECT * FROM faces WHERE photo_id=?", (pid,)).fetchall()
            assert len(faces_after) == 0
            ok("delete_photo_cleans_faces")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("delete_photo_cleans_faces", e)


def test_delete_photo_cleans_album_membership():
    try:
        db, tmp = make_db()
        try:
            pid = upsert(db, "/a/img.jpg")
            aid = db.create_album("Test Album")
            db.add_photo_to_album(aid, pid)
            assert db.count_album_photos(aid) == 1
            db.delete_photo(pid)
            assert db.count_album_photos(aid) == 0
            ok("delete_photo_cleans_album_membership")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("delete_photo_cleans_album_membership", e)


def test_delete_photo_nonexistent():
    try:
        db, tmp = make_db()
        try:
            result = db.delete_photo(99999)
            assert result is False
            ok("delete_photo_nonexistent")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("delete_photo_nonexistent", e)


def test_delete_photo_file_on_disk():
    try:
        db, tmp = make_db()
        try:
            # Create a real temp file
            fpath = os.path.join(tmp, "real.jpg")
            with open(fpath, "wb") as f:
                f.write(b"fake")
            pid = upsert(db, fpath)
            assert os.path.exists(fpath)
            db.delete_photo(pid, delete_file=True)
            assert not os.path.exists(fpath)
            ok("delete_photo_file_on_disk")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("delete_photo_file_on_disk", e)


def test_stats_reflect_duplicate_groups():
    try:
        db, tmp = make_db()
        try:
            assert db.get_stats()["duplicate_groups"] == 0
            make_dup_group(db, ["/a/img1.jpg", "/a/img2.jpg"])
            assert db.get_stats()["duplicate_groups"] == 1
            ok("stats_reflect_duplicate_groups")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("stats_reflect_duplicate_groups", e)


# ── B: DuplicateView UI ───────────────────────────────────────────────────────

print("\n=== B: DuplicateView UI ===")


def test_duplicate_view_init():
    try:
        app = setup_qt()
        from ui.duplicate_view import DuplicateView
        db, tmp = make_db()
        try:
            dv = DuplicateView(db)
            assert dv is not None
            ok("duplicate_view_init")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("duplicate_view_init", e)


def test_duplicate_view_refresh_empty():
    try:
        app = setup_qt()
        from ui.duplicate_view import DuplicateView
        db, tmp = make_db()
        try:
            dv = DuplicateView(db)
            dv.refresh()
            assert dv.group_list.count() == 0
            assert dv.action_bar.isHidden()
            ok("duplicate_view_refresh_empty")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("duplicate_view_refresh_empty", e)


def test_duplicate_view_shows_groups():
    try:
        app = setup_qt()
        from ui.duplicate_view import DuplicateView
        db, tmp = make_db()
        try:
            make_dup_group(db, ["/a/img1.jpg", "/a/img2.jpg"])
            make_dup_group(db, ["/a/img3.jpg", "/a/img4.jpg"])
            dv = DuplicateView(db)
            dv.refresh()
            assert dv.group_list.count() == 2
            ok("duplicate_view_shows_groups")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("duplicate_view_shows_groups", e)


def test_duplicate_view_select_shows_cards():
    try:
        app = setup_qt()
        from ui.duplicate_view import DuplicateView
        db, tmp = make_db()
        try:
            make_dup_group(db, ["/a/img1.jpg", "/a/img2.jpg", "/a/img3.jpg"])
            dv = DuplicateView(db)
            dv.refresh()
            # First group auto-selected; action bar should be visible
            assert not dv.action_bar.isHidden()
            ok("duplicate_view_select_shows_cards")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("duplicate_view_select_shows_cards", e)


def test_duplicate_view_keep_all():
    try:
        app = setup_qt()
        from ui.duplicate_view import DuplicateView
        db, tmp = make_db()
        try:
            gid, pids = make_dup_group(db, ["/a/img1.jpg", "/a/img2.jpg"])
            dv = DuplicateView(db)
            dv.refresh()
            dv._keep_all()
            # Group dismissed, both photos still exist
            assert len(db.get_duplicate_groups()) == 0
            for pid in pids:
                assert db.get_photo(pid) is not None
            ok("duplicate_view_keep_all")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("duplicate_view_keep_all", e)


def test_duplicate_view_keep_best_by_resolution():
    try:
        app = setup_qt()
        from ui.duplicate_view import DuplicateView
        db, tmp = make_db()
        try:
            gid = db.get_or_create_duplicate_group("res_hash")
            pid_lo = upsert(db, "/a/lo.jpg", w=640, h=480, size=100_000)
            pid_hi = upsert(db, "/a/hi.jpg", w=4032, h=3024, size=5_000_000)
            db.add_to_duplicate_group(gid, pid_lo)
            db.add_to_duplicate_group(gid, pid_hi)
            dv = DuplicateView(db)
            dv.refresh()
            # _keep_best triggers keep_one which asks QMessageBox (mocked to Yes)
            dv._keep_best()
            # hi-res should survive, lo-res deleted
            assert db.get_photo(pid_hi) is not None
            assert db.get_photo(pid_lo) is None
            assert len(db.get_duplicate_groups()) == 0
            ok("duplicate_view_keep_best_by_resolution")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("duplicate_view_keep_best_by_resolution", e)


def test_duplicate_view_delete_one_dismisses_when_one_left():
    try:
        app = setup_qt()
        from ui.duplicate_view import DuplicateView
        db, tmp = make_db()
        try:
            gid, pids = make_dup_group(db, ["/a/imgA.jpg", "/a/imgB.jpg"])
            dv = DuplicateView(db)
            dv.refresh()
            # Delete first photo — only one remains → group should be dismissed
            dv._delete_one(gid, pids[0])
            assert db.get_photo(pids[0]) is None
            assert db.get_photo(pids[1]) is not None
            assert len(db.get_duplicate_groups()) == 0
            ok("duplicate_view_delete_one_dismisses_when_one_left")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("duplicate_view_delete_one_dismisses_when_one_left", e)


def test_duplicate_view_delete_one_keeps_group_with_2_left():
    try:
        app = setup_qt()
        from ui.duplicate_view import DuplicateView
        db, tmp = make_db()
        try:
            gid, pids = make_dup_group(db, ["/a/p1.jpg", "/a/p2.jpg", "/a/p3.jpg"])
            dv = DuplicateView(db)
            dv.refresh()
            dv._delete_one(gid, pids[0])
            assert db.get_photo(pids[0]) is None
            # Group still has 2 members → should remain
            remaining = db.get_duplicate_group_photos(gid)
            assert len(remaining) == 2
            ok("duplicate_view_delete_one_keeps_group_with_2_left")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("duplicate_view_delete_one_keeps_group_with_2_left", e)


def test_duplicate_view_skip_advances():
    try:
        app = setup_qt()
        from ui.duplicate_view import DuplicateView
        db, tmp = make_db()
        try:
            make_dup_group(db, ["/a/g1a.jpg", "/a/g1b.jpg"])
            make_dup_group(db, ["/a/g2a.jpg", "/a/g2b.jpg"])
            dv = DuplicateView(db)
            dv.refresh()
            assert dv.group_list.count() == 2
            dv._skip()
            # Both groups still present after skip
            assert dv.group_list.count() == 2
            ok("duplicate_view_skip_advances")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("duplicate_view_skip_advances", e)


def test_duplicate_view_no_action_when_no_group():
    try:
        app = setup_qt()
        from ui.duplicate_view import DuplicateView
        db, tmp = make_db()
        try:
            dv = DuplicateView(db)
            dv.refresh()
            # Should not raise even when no group is selected
            dv._keep_best()
            dv._keep_all()
            dv._skip()
            ok("duplicate_view_no_action_when_no_group")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("duplicate_view_no_action_when_no_group", e)


# ── C: MainWindow integration ─────────────────────────────────────────────────

print("\n=== C: MainWindow Integration ===")


def test_main_window_has_5_nav_items():
    try:
        app = setup_qt()
        from ui.main_window import MainWindow, _Sidebar
        assert len(_Sidebar.NAV_ITEMS) == 8
        ok("main_window_has_5_nav_items")
    except Exception as e:
        fail("main_window_has_5_nav_items", e)


def test_main_window_navigate_to_duplicates():
    try:
        app = setup_qt()
        from ui.main_window import MainWindow
        import tempfile
        tmp = tempfile.mkdtemp()
        try:
            mw = MainWindow(app_dir=tmp)
            mw._navigate(4)
            assert mw.stack.currentIndex() == 4
            ok("main_window_navigate_to_duplicates")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("main_window_navigate_to_duplicates", e)


def test_main_window_duplicate_view_refreshes_on_nav():
    try:
        app = setup_qt()
        from ui.main_window import MainWindow
        import tempfile
        tmp = tempfile.mkdtemp()
        try:
            mw = MainWindow(app_dir=tmp)
            # Add a duplicate group directly to the mw's db
            gid = mw.db.get_or_create_duplicate_group("test_hash")
            p1 = mw.db.upsert_photo({"file_path": "/x/a.jpg", "file_name": "a.jpg", "sha256_hash": "h1"})
            p2 = mw.db.upsert_photo({"file_path": "/x/b.jpg", "file_name": "b.jpg", "sha256_hash": "h2"})
            mw.db.add_to_duplicate_group(gid, p1)
            mw.db.add_to_duplicate_group(gid, p2)
            # Navigate to duplicates — should refresh automatically
            mw._navigate(4)
            assert mw.duplicate_view.group_list.count() == 1
            ok("main_window_duplicate_view_refreshes_on_nav")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("main_window_duplicate_view_refreshes_on_nav", e)


# ── Run all ───────────────────────────────────────────────────────────────────

test_get_duplicate_groups_empty()
test_get_duplicate_groups_only_multi()
test_get_duplicate_group_photos()
test_set_duplicate_master()
test_dismiss_duplicate_group()
test_delete_photo_removes_record()
test_delete_photo_cleans_dup_membership()
test_delete_photo_cleans_faces()
test_delete_photo_cleans_album_membership()
test_delete_photo_nonexistent()
test_delete_photo_file_on_disk()
test_stats_reflect_duplicate_groups()

test_duplicate_view_init()
test_duplicate_view_refresh_empty()
test_duplicate_view_shows_groups()
test_duplicate_view_select_shows_cards()
test_duplicate_view_keep_all()
test_duplicate_view_keep_best_by_resolution()
test_duplicate_view_delete_one_dismisses_when_one_left()
test_duplicate_view_delete_one_keeps_group_with_2_left()
test_duplicate_view_skip_advances()
test_duplicate_view_no_action_when_no_group()

test_main_window_has_5_nav_items()
test_main_window_navigate_to_duplicates()
test_main_window_duplicate_view_refreshes_on_nav()

total = len(PASS) + len(FAIL)
print(f"\nDuplicate Results: {len(PASS)} passed, {len(FAIL)} failed")
if not FAIL:
    print("ALL PASSED")
else:
    print(f"FAILURES: {FAIL}")
