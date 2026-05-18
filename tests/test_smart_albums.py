"""Tests for Stage 3c: Smart Albums — DB methods + UI."""
import os
import sys
import tempfile
import shutil
import json

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


def upsert(db, path, sha=None, exif_date=None, camera=None):
    data = {
        "file_path": path,
        "file_name": os.path.basename(path),
        "sha256_hash": sha or ("hash_" + os.path.basename(path)),
    }
    if exif_date:
        data["exif_date"] = exif_date
    if camera:
        data["camera_model"] = camera
    return db.upsert_photo(data)


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


# ── A: search_photos new filters ──────────────────────────────────────────────

print("=== A: search_photos new filters ===")


def test_search_filter_camera_model():
    try:
        db, tmp = make_db()
        try:
            pid1 = upsert(db, "/a/canon.jpg", camera="Canon EOS R5")
            pid2 = upsert(db, "/a/nikon.jpg", camera="Nikon Z6")
            pid3 = upsert(db, "/a/nocam.jpg")
            results = db.search_photos(filters={"camera_model": "Canon EOS R5"})
            ids = [r["id"] for r in results]
            assert pid1 in ids
            assert pid2 not in ids
            assert pid3 not in ids
            ok("search_filter_camera_model")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("search_filter_camera_model", e)


def test_search_filter_no_date():
    try:
        db, tmp = make_db()
        try:
            pid_dated = upsert(db, "/a/dated.jpg", exif_date="2023-06-01 12:00:00")
            pid_nodates = upsert(db, "/a/nodate.jpg")
            results = db.search_photos(filters={"no_date": True})
            ids = [r["id"] for r in results]
            assert pid_nodates in ids
            assert pid_dated not in ids
            ok("search_filter_no_date")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("search_filter_no_date", e)


def test_search_filter_unassigned_faces():
    try:
        db, tmp = make_db()
        try:
            pid_unassigned = upsert(db, "/a/face.jpg")
            pid_assigned = upsert(db, "/a/known.jpg")
            pid_no_face = upsert(db, "/a/noface.jpg")
            # Unassigned face
            db.insert_face({"photo_id": pid_unassigned, "bbox_top": 10, "bbox_left": 10,
                             "bbox_bottom": 60, "bbox_right": 60})
            # Assigned face
            person_id = db.create_person("Alice")
            fid = db.insert_face({"photo_id": pid_assigned, "bbox_top": 5, "bbox_left": 5,
                                   "bbox_bottom": 55, "bbox_right": 55})
            db.confirm_face(fid, person_id)
            results = db.search_photos(filters={"unassigned_faces": True})
            ids = [r["id"] for r in results]
            assert pid_unassigned in ids
            assert pid_assigned not in ids
            assert pid_no_face not in ids
            ok("search_filter_unassigned_faces")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("search_filter_unassigned_faces", e)


def test_search_filter_has_camera():
    try:
        db, tmp = make_db()
        try:
            pid_cam = upsert(db, "/a/cam.jpg", camera="Sony A7")
            pid_no = upsert(db, "/a/no.jpg")
            results = db.search_photos(filters={"has_camera": True})
            ids = [r["id"] for r in results]
            assert pid_cam in ids
            assert pid_no not in ids
            ok("search_filter_has_camera")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("search_filter_has_camera", e)


# ── B: DB Smart Album Methods ─────────────────────────────────────────────────

print("\n=== B: DB Smart Album Methods ===")


def test_create_and_get_smart_album():
    try:
        db, tmp = make_db()
        try:
            sa_id = db.create_smart_album("Recent", {"date_from": "2024-01-01"}, icon="📅")
            albums = db.get_all_smart_albums()
            assert len(albums) == 1
            assert albums[0]["id"] == sa_id
            assert albums[0]["name"] == "Recent"
            assert albums[0]["icon"] == "📅"
            ok("create_and_get_smart_album")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("create_and_get_smart_album", e)


def test_update_smart_album_name():
    try:
        db, tmp = make_db()
        try:
            sa_id = db.create_smart_album("Old Name", {})
            db.update_smart_album(sa_id, name="New Name")
            albums = db.get_all_smart_albums()
            assert albums[0]["name"] == "New Name"
            ok("update_smart_album_name")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("update_smart_album_name", e)


def test_update_smart_album_criteria():
    try:
        db, tmp = make_db()
        try:
            sa_id = db.create_smart_album("Test", {"no_date": True})
            db.update_smart_album(sa_id, criteria={"has_camera": True})
            albums = db.get_all_smart_albums()
            crit = json.loads(albums[0]["criteria"])
            assert crit.get("has_camera") is True
            assert "no_date" not in crit
            ok("update_smart_album_criteria")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("update_smart_album_criteria", e)


def test_delete_smart_album():
    try:
        db, tmp = make_db()
        try:
            sa_id = db.create_smart_album("Delete Me", {})
            assert len(db.get_all_smart_albums()) == 1
            db.delete_smart_album(sa_id)
            assert len(db.get_all_smart_albums()) == 0
            ok("delete_smart_album")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("delete_smart_album", e)


def test_get_smart_album_photos():
    try:
        db, tmp = make_db()
        try:
            pid1 = upsert(db, "/a/cam.jpg", camera="Sony A7")
            pid2 = upsert(db, "/a/nocam.jpg")
            sa_id = db.create_smart_album("With Camera", {"has_camera": True})
            photos = db.get_smart_album_photos(sa_id)
            ids = [p["id"] for p in photos]
            assert pid1 in ids
            assert pid2 not in ids
            ok("get_smart_album_photos")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("get_smart_album_photos", e)


def test_get_smart_album_photos_invalid_id():
    try:
        db, tmp = make_db()
        try:
            result = db.get_smart_album_photos(99999)
            assert result == []
            ok("get_smart_album_photos_invalid_id")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("get_smart_album_photos_invalid_id", e)


def test_ensure_builtin_smart_albums():
    try:
        db, tmp = make_db()
        try:
            db.ensure_builtin_smart_albums()
            albums = db.get_all_smart_albums()
            names = [a["name"] for a in albums]
            assert any("This Month" in n for n in names)
            assert any("This Year" in n for n in names)
            assert any("Unassigned" in n for n in names)
            assert any("No Date" in n for n in names)
            assert any("Camera" in n for n in names)
            ok("ensure_builtin_smart_albums")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("ensure_builtin_smart_albums", e)


def test_ensure_builtin_idempotent():
    try:
        db, tmp = make_db()
        try:
            db.ensure_builtin_smart_albums()
            count1 = len(db.get_all_smart_albums())
            db.ensure_builtin_smart_albums()
            count2 = len(db.get_all_smart_albums())
            assert count1 == count2
            ok("ensure_builtin_idempotent")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("ensure_builtin_idempotent", e)


def test_builtin_albums_are_flagged():
    try:
        db, tmp = make_db()
        try:
            db.ensure_builtin_smart_albums()
            user_id = db.create_smart_album("Mine", {}, is_builtin=False)
            albums = db.get_all_smart_albums()
            builtin = [a for a in albums if a["is_builtin"]]
            user = [a for a in albums if not a["is_builtin"]]
            assert len(builtin) >= 5
            assert len(user) == 1
            assert user[0]["id"] == user_id
            ok("builtin_albums_are_flagged")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("builtin_albums_are_flagged", e)


# ── C: SmartAlbumView UI ──────────────────────────────────────────────────────

print("\n=== C: SmartAlbumView UI ===")


def test_smart_album_view_init():
    try:
        app = setup_qt()
        from ui.smart_album_view import SmartAlbumView
        db, tmp = make_db()
        try:
            sv = SmartAlbumView(db)
            assert sv is not None
            ok("smart_album_view_init")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("smart_album_view_init", e)


def test_smart_album_view_refresh_creates_builtins():
    try:
        app = setup_qt()
        from ui.smart_album_view import SmartAlbumView
        db, tmp = make_db()
        try:
            sv = SmartAlbumView(db)
            sv.refresh()
            assert sv.album_list.count() >= 5
            ok("smart_album_view_refresh_creates_builtins")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("smart_album_view_refresh_creates_builtins", e)


def test_smart_album_view_shows_user_albums():
    try:
        app = setup_qt()
        from ui.smart_album_view import SmartAlbumView
        db, tmp = make_db()
        try:
            db.create_smart_album("My Custom", {"no_date": True})
            sv = SmartAlbumView(db)
            sv.refresh()
            texts = [sv.album_list.item(i).text() for i in range(sv.album_list.count())]
            assert any("My Custom" in t for t in texts)
            ok("smart_album_view_shows_user_albums")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("smart_album_view_shows_user_albums", e)


def test_smart_album_view_loads_photos_on_select():
    try:
        app = setup_qt()
        from ui.smart_album_view import SmartAlbumView
        db, tmp = make_db()
        try:
            upsert(db, "/a/cam1.jpg", camera="Canon")
            upsert(db, "/a/cam2.jpg", camera="Canon")
            upsert(db, "/a/nocam.jpg")
            sa_id = db.create_smart_album("Canon Shots", {"camera_model": "Canon"})
            sv = SmartAlbumView(db)
            sv.refresh()
            sv._load_album(sa_id)
            assert sv.grid.count() == 2
            ok("smart_album_view_loads_photos_on_select")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("smart_album_view_loads_photos_on_select", e)


def test_smart_album_view_header_shows_name():
    try:
        app = setup_qt()
        from ui.smart_album_view import SmartAlbumView
        db, tmp = make_db()
        try:
            sa_id = db.create_smart_album("No Date Photos", {"no_date": True}, icon="❓")
            sv = SmartAlbumView(db)
            sv.refresh()
            sv._load_album(sa_id)
            assert "No Date Photos" in sv.header_lbl.text()
            assert not sv.header_bar.isHidden()
            ok("smart_album_view_header_shows_name")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("smart_album_view_header_shows_name", e)


def test_smart_album_view_refresh_restores_selection():
    try:
        app = setup_qt()
        from ui.smart_album_view import SmartAlbumView
        db, tmp = make_db()
        try:
            sa_id = db.create_smart_album("Cam", {"has_camera": True})
            sv = SmartAlbumView(db)
            sv.refresh()
            sv._current_sa_id = sa_id
            sv.refresh()
            assert sv._current_sa_id == sa_id
            ok("smart_album_view_refresh_restores_selection")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("smart_album_view_refresh_restores_selection", e)


def test_smart_album_view_delete_user_album():
    try:
        app = setup_qt()
        from ui.smart_album_view import SmartAlbumView
        db, tmp = make_db()
        try:
            sa_id = db.create_smart_album("Delete Me", {})
            sv = SmartAlbumView(db)
            sv.refresh()
            sv._delete(sa_id)
            assert len(db.get_all_smart_albums()) == 5  # only builtins remain
            ok("smart_album_view_delete_user_album")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("smart_album_view_delete_user_album", e)


def test_smart_album_view_rename_user_album():
    try:
        app = setup_qt()
        from ui.smart_album_view import SmartAlbumView
        from unittest.mock import patch
        db, tmp = make_db()
        try:
            sa_id = db.create_smart_album("Old", {})
            sv = SmartAlbumView(db)
            sv.refresh()
            with patch("PyQt6.QtWidgets.QInputDialog.getText", return_value=("New Name", True)):
                sv._rename(sa_id)
            albums = db.get_all_smart_albums()
            user = [a for a in albums if not a["is_builtin"]]
            assert user[0]["name"] == "New Name"
            ok("smart_album_view_rename_user_album")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("smart_album_view_rename_user_album", e)


# ── D: MainWindow integration ─────────────────────────────────────────────────

print("\n=== D: MainWindow Integration ===")


def test_main_window_has_7_nav_items():
    try:
        app = setup_qt()
        from ui.main_window import _Sidebar
        assert len(_Sidebar.NAV_ITEMS) == 7
        ok("main_window_has_7_nav_items")
    except Exception as e:
        fail("main_window_has_7_nav_items", e)


def test_main_window_navigate_to_smart_albums():
    try:
        app = setup_qt()
        from ui.main_window import MainWindow
        tmp = tempfile.mkdtemp()
        try:
            mw = MainWindow(app_dir=tmp)
            mw._navigate(6)
            assert mw.stack.currentIndex() == 6
            ok("main_window_navigate_to_smart_albums")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("main_window_navigate_to_smart_albums", e)


def test_main_window_smart_albums_refreshes_on_nav():
    try:
        app = setup_qt()
        from ui.main_window import MainWindow
        tmp = tempfile.mkdtemp()
        try:
            mw = MainWindow(app_dir=tmp)
            mw._navigate(6)
            # Builtins should be created on first nav
            assert mw.smart_album_view.album_list.count() >= 5
            ok("main_window_smart_albums_refreshes_on_nav")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("main_window_smart_albums_refreshes_on_nav", e)


# ── Run all ───────────────────────────────────────────────────────────────────

test_search_filter_camera_model()
test_search_filter_no_date()
test_search_filter_unassigned_faces()
test_search_filter_has_camera()

test_create_and_get_smart_album()
test_update_smart_album_name()
test_update_smart_album_criteria()
test_delete_smart_album()
test_get_smart_album_photos()
test_get_smart_album_photos_invalid_id()
test_ensure_builtin_smart_albums()
test_ensure_builtin_idempotent()
test_builtin_albums_are_flagged()

test_smart_album_view_init()
test_smart_album_view_refresh_creates_builtins()
test_smart_album_view_shows_user_albums()
test_smart_album_view_loads_photos_on_select()
test_smart_album_view_header_shows_name()
test_smart_album_view_refresh_restores_selection()
test_smart_album_view_delete_user_album()
test_smart_album_view_rename_user_album()

test_main_window_has_7_nav_items()
test_main_window_navigate_to_smart_albums()
test_main_window_smart_albums_refreshes_on_nav()

print(f"\nSmart Album Results: {len(PASS)} passed, {len(FAIL)} failed")
if not FAIL:
    print("ALL PASSED")
else:
    print(f"FAILURES: {FAIL}")
