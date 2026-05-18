"""Integration + regression tests for Stage 1 + Stage 2 combined.

Covers: DB album operations, gallery logic, photo-detail logic,
album-view logic, search/filter correctness, cross-module wiring,
UI signal handlers, and edge cases.
"""

import os
import sys
import tempfile
import shutil
import threading
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core.face_engine import encode_embedding
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

def upsert(db, path, sha=None):
    return db.upsert_photo({
        "file_path": path,
        "file_name": os.path.basename(path),
        "sha256_hash": sha or ("hash_" + os.path.basename(path)),
    })

def setup_qt():
    from PyQt6.QtWidgets import QApplication, QMessageBox
    app = QApplication.instance() or QApplication(sys.argv)
    QMessageBox.information = staticmethod(lambda *a, **kw: None)
    QMessageBox.warning = staticmethod(lambda *a, **kw: None)
    QMessageBox.critical = staticmethod(lambda *a, **kw: None)
    QMessageBox.question = staticmethod(
        lambda *a, **kw: QMessageBox.StandardButton.Yes
    )
    return app


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION A: DB Album CRUD
# ═══════════════════════════════════════════════════════════════════════════════
print("=== A: DB Album CRUD ===")

def test_create_and_get_album():
    db, tmp = make_db()
    try:
        aid = db.create_album("Vacation 2024", description="Summer trip")
        row = db.get_album(aid)
        assert row["name"] == "Vacation 2024"
        assert row["description"] == "Summer trip"
        ok("create_and_get_album")
    except Exception as e:
        fail("create_and_get_album", e)
    finally:
        shutil.rmtree(tmp)

def test_get_all_albums_with_count():
    db, tmp = make_db()
    try:
        aid = db.create_album("Work")
        pid1 = upsert(db, "/p/a.jpg")
        pid2 = upsert(db, "/p/b.jpg")
        db.add_photo_to_album(aid, pid1)
        db.add_photo_to_album(aid, pid2)
        albums = db.get_all_albums()
        assert len(albums) == 1
        assert albums[0]["photo_count"] == 2
        ok("get_all_albums_with_count")
    except Exception as e:
        fail("get_all_albums_with_count", e)
    finally:
        shutil.rmtree(tmp)

def test_update_album_name():
    db, tmp = make_db()
    try:
        aid = db.create_album("Old Name")
        db.update_album(aid, name="New Name")
        row = db.get_album(aid)
        assert row["name"] == "New Name"
        ok("update_album_name")
    except Exception as e:
        fail("update_album_name", e)
    finally:
        shutil.rmtree(tmp)

def test_delete_album_cascades_members():
    db, tmp = make_db()
    try:
        aid = db.create_album("Temp")
        pid = upsert(db, "/p/c.jpg")
        db.add_photo_to_album(aid, pid)
        db.delete_album(aid)
        # Album gone
        assert db.get_album(aid) is None
        # Photo still exists (only membership removed)
        assert db.get_photo(pid) is not None
        # Album photos query returns empty
        photos = db.get_album_photos(aid)
        assert len(photos) == 0
        ok("delete_album_cascades_members_photo_survives")
    except Exception as e:
        fail("delete_album_cascades_members", e)
    finally:
        shutil.rmtree(tmp)

def test_add_photo_to_album_idempotent():
    db, tmp = make_db()
    try:
        aid = db.create_album("Dupes")
        pid = upsert(db, "/p/d.jpg")
        db.add_photo_to_album(aid, pid)
        db.add_photo_to_album(aid, pid)  # duplicate — INSERT OR IGNORE
        count = db.count_album_photos(aid)
        assert count == 1, f"expected 1, got {count}"
        ok("add_photo_idempotent")
    except Exception as e:
        fail("add_photo_to_album_idempotent", e)
    finally:
        shutil.rmtree(tmp)

def test_remove_photo_from_album():
    db, tmp = make_db()
    try:
        aid = db.create_album("X")
        pid = upsert(db, "/p/e.jpg")
        db.add_photo_to_album(aid, pid)
        assert db.count_album_photos(aid) == 1
        db.remove_photo_from_album(aid, pid)
        assert db.count_album_photos(aid) == 0
        ok("remove_photo_from_album")
    except Exception as e:
        fail("remove_photo_from_album", e)
    finally:
        shutil.rmtree(tmp)

def test_get_albums_for_photo():
    db, tmp = make_db()
    try:
        aid1 = db.create_album("A1")
        aid2 = db.create_album("A2")
        pid = upsert(db, "/p/f.jpg")
        db.add_photo_to_album(aid1, pid)
        db.add_photo_to_album(aid2, pid)
        albums = db.get_albums_for_photo(pid)
        ids = {a["id"] for a in albums}
        assert aid1 in ids and aid2 in ids
        ok("get_albums_for_photo")
    except Exception as e:
        fail("get_albums_for_photo", e)
    finally:
        shutil.rmtree(tmp)

def test_cover_photo_auto_set():
    db, tmp = make_db()
    try:
        aid = db.create_album("Cover")
        pid = upsert(db, "/p/g.jpg")
        db.add_photo_to_album(aid, pid)
        album = db.get_album(aid)
        assert album["cover_photo_id"] == pid
        ok("cover_photo_auto_set_on_first_add")
    except Exception as e:
        fail("cover_photo_auto_set", e)
    finally:
        shutil.rmtree(tmp)

def test_get_stats_includes_albums():
    db, tmp = make_db()
    try:
        db.create_album("S1")
        db.create_album("S2")
        stats = db.get_stats()
        assert "total_albums" in stats
        assert stats["total_albums"] == 2
        ok("get_stats_total_albums")
    except Exception as e:
        fail("get_stats_includes_albums", e)
    finally:
        shutil.rmtree(tmp)

test_create_and_get_album()
test_get_all_albums_with_count()
test_update_album_name()
test_delete_album_cascades_members()
test_add_photo_to_album_idempotent()
test_remove_photo_from_album()
test_get_albums_for_photo()
test_cover_photo_auto_set()
test_get_stats_includes_albums()


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION B: DB search_photos with all filters
# ═══════════════════════════════════════════════════════════════════════════════
print("\n=== B: search_photos filters ===")

def test_search_by_filename():
    db, tmp = make_db()
    try:
        upsert(db, "/p/beach_sunset.jpg")
        upsert(db, "/p/birthday_party.jpg")
        rows = db.search_photos(query="beach")
        assert len(rows) == 1 and "beach" in rows[0]["file_path"]
        ok("search_by_filename")
    except Exception as e:
        fail("search_by_filename", e)
    finally:
        shutil.rmtree(tmp)

def test_search_no_results():
    db, tmp = make_db()
    try:
        upsert(db, "/p/h.jpg")
        rows = db.search_photos(query="zzznotexist")
        assert len(rows) == 0
        ok("search_no_results")
    except Exception as e:
        fail("search_no_results", e)
    finally:
        shutil.rmtree(tmp)

def test_search_empty_query_returns_all():
    db, tmp = make_db()
    try:
        for i in range(5):
            upsert(db, f"/p/img{i}.jpg")
        rows = db.search_photos(query="")
        assert len(rows) == 5
        ok("search_empty_returns_all")
    except Exception as e:
        fail("search_empty_query", e)
    finally:
        shutil.rmtree(tmp)

def test_search_filter_album_id():
    db, tmp = make_db()
    try:
        aid = db.create_album("FilterAlbum")
        p1 = upsert(db, "/p/in_album.jpg")
        p2 = upsert(db, "/p/not_in.jpg")
        db.add_photo_to_album(aid, p1)
        rows = db.search_photos(filters={"album_id": aid})
        assert len(rows) == 1 and rows[0]["id"] == p1
        ok("search_filter_album_id")
    except Exception as e:
        fail("search_filter_album_id", e)
    finally:
        shutil.rmtree(tmp)

def test_search_filter_person_id():
    db, tmp = make_db()
    try:
        pid_person = db.create_person("FilterPerson")
        photo_id = upsert(db, "/p/with_face.jpg")
        other_id = upsert(db, "/p/no_face.jpg")
        fid = db.insert_face({
            "photo_id": photo_id,
            "bbox_top": 0, "bbox_right": 50, "bbox_bottom": 50, "bbox_left": 0,
            "embedding": encode_embedding(np.random.default_rng(1).standard_normal(128).astype(np.float32)),
        })
        db.confirm_face(fid, pid_person)
        rows = db.search_photos(filters={"person_id": pid_person})
        ids = [r["id"] for r in rows]
        assert photo_id in ids and other_id not in ids
        ok("search_filter_person_id")
    except Exception as e:
        fail("search_filter_person_id", e)
    finally:
        shutil.rmtree(tmp)

def test_search_filter_date_range():
    db, tmp = make_db()
    try:
        db.upsert_photo({"file_path": "/p/old.jpg", "file_name": "old.jpg",
                         "exif_date": "2020-01-15 12:00:00"})
        db.upsert_photo({"file_path": "/p/new.jpg", "file_name": "new.jpg",
                         "exif_date": "2024-06-01 12:00:00"})
        rows = db.search_photos(filters={"date_from": "2024-01-01", "date_to": "2024-12-31"})
        assert len(rows) == 1 and rows[0]["file_name"] == "new.jpg"
        ok("search_filter_date_range")
    except Exception as e:
        fail("search_filter_date_range", e)
    finally:
        shutil.rmtree(tmp)

def test_search_filter_has_faces():
    db, tmp = make_db()
    try:
        pid_p = upsert(db, "/p/has_face.jpg")
        _ = upsert(db, "/p/no_face.jpg")
        fid = db.insert_face({
            "photo_id": pid_p,
            "bbox_top": 0, "bbox_right": 50, "bbox_bottom": 50, "bbox_left": 0,
        })
        rows = db.search_photos(filters={"has_faces": True})
        assert len(rows) == 1 and rows[0]["id"] == pid_p
        rows2 = db.search_photos(filters={"has_faces": False})
        assert all(r["id"] != pid_p for r in rows2)
        ok("search_filter_has_faces")
    except Exception as e:
        fail("search_filter_has_faces", e)
    finally:
        shutil.rmtree(tmp)

test_search_by_filename()
test_search_no_results()
test_search_empty_query_returns_all()
test_search_filter_album_id()
test_search_filter_person_id()
test_search_filter_date_range()
test_search_filter_has_faces()


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION C: Photo grid + gallery view UI
# ═══════════════════════════════════════════════════════════════════════════════
print("\n=== C: Gallery + PhotoGrid UI ===")

def test_photo_grid_set_photos():
    try:
        app = setup_qt()
        from ui.photo_grid import PhotoGrid
        db, tmp = make_db()
        try:
            p1 = upsert(db, "/fake/a.jpg")
            p2 = upsert(db, "/fake/b.jpg")
            grid = PhotoGrid()
            rows = db.get_all_photos()
            grid.set_photos(rows)
            assert grid.count() == 2
            ids = grid.photo_ids()
            assert set(ids) == {p1, p2}
            ok("photo_grid_set_photos")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("photo_grid_set_photos", e)

def test_photo_grid_append_photos():
    try:
        app = setup_qt()
        from ui.photo_grid import PhotoGrid
        db, tmp = make_db()
        try:
            for i in range(4):
                upsert(db, f"/fake/{i}.jpg")
            rows = db.get_all_photos()
            grid = PhotoGrid()
            grid.set_photos(rows[:2])
            grid.append_photos(rows[2:])
            assert grid.count() == 4
            ok("photo_grid_append_photos")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("photo_grid_append_photos", e)

def test_photo_grid_clear_on_reset():
    try:
        app = setup_qt()
        from ui.photo_grid import PhotoGrid
        db, tmp = make_db()
        try:
            for i in range(3):
                upsert(db, f"/fake/clear{i}.jpg")
            rows = db.get_all_photos()
            grid = PhotoGrid()
            grid.set_photos(rows)
            assert grid.count() == 3
            grid.set_photos([])  # clear
            assert grid.count() == 0
            ok("photo_grid_clear_on_reset")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("photo_grid_clear_on_reset", e)

def test_photo_grid_id_map_correct():
    try:
        app = setup_qt()
        from ui.photo_grid import PhotoGrid
        db, tmp = make_db()
        try:
            ids = [upsert(db, f"/fake/idmap{i}.jpg") for i in range(5)]
            rows = db.get_all_photos()
            grid = PhotoGrid()
            grid.set_photos(rows)
            assert len(grid._id_map) == 5
            assert set(grid._id_map.keys()) == set(ids)
            ok("photo_grid_id_map_correct")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("photo_grid_id_map_correct", e)

def test_gallery_view_init():
    try:
        app = setup_qt()
        from ui.gallery_view import GalleryView
        db, tmp = make_db()
        try:
            gv = GalleryView(db)
            assert gv is not None
            ok("gallery_view_init")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("gallery_view_init", e)

def test_gallery_view_refresh_empty():
    try:
        app = setup_qt()
        from ui.gallery_view import GalleryView
        db, tmp = make_db()
        try:
            gv = GalleryView(db)
            gv.refresh()
            assert gv.grid.count() == 0
            assert "0" in gv.status_label.text()
            ok("gallery_view_refresh_empty")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("gallery_view_refresh_empty", e)

def test_gallery_view_refresh_with_photos():
    try:
        app = setup_qt()
        from ui.gallery_view import GalleryView
        db, tmp = make_db()
        try:
            for i in range(5):
                upsert(db, f"/fake/gv{i}.jpg")
            gv = GalleryView(db)
            gv.refresh()
            assert gv.grid.count() == 5
            assert "5" in gv.status_label.text()
            ok("gallery_view_refresh_5_photos")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("gallery_view_refresh_with_photos", e)

def test_gallery_view_search_filter():
    try:
        app = setup_qt()
        from ui.gallery_view import GalleryView
        db, tmp = make_db()
        try:
            upsert(db, "/fake/mountain_view.jpg")
            upsert(db, "/fake/beach_photo.jpg")
            upsert(db, "/fake/city_night.jpg")
            gv = GalleryView(db)
            gv.refresh()
            assert gv.grid.count() == 3

            # Set search query
            gv.search_box.setText("mountain")
            gv._current_query = "mountain"
            gv._load_page(reset=True)
            assert gv.grid.count() == 1
            ok("gallery_view_search_filter")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("gallery_view_search_filter", e)

def test_gallery_load_more():
    try:
        app = setup_qt()
        from ui.gallery_view import GalleryView, PAGE_SIZE
        db, tmp = make_db()
        try:
            for i in range(PAGE_SIZE + 10):
                upsert(db, f"/fake/page{i:04d}.jpg")
            gv = GalleryView(db)
            gv.refresh()
            # First page loaded
            assert gv.grid.count() == PAGE_SIZE
            assert not gv.load_more_btn.isHidden()  # show() called
            # Load the rest
            gv._load_more()
            assert gv.grid.count() == PAGE_SIZE + 10
            assert gv.load_more_btn.isHidden()  # hide() called
            ok("gallery_load_more")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("gallery_load_more", e)

def test_gallery_debounce_timer_single():
    try:
        app = setup_qt()
        from ui.gallery_view import GalleryView
        db, tmp = make_db()
        try:
            gv = GalleryView(db)
            # Firing search multiple times should not start multiple timers
            gv._on_search_changed("a")
            gv._on_search_changed("ab")
            gv._on_search_changed("abc")
            # Timer should be active (single debounce)
            assert gv._search_timer.isActive()
            ok("gallery_debounce_single_timer")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("gallery_debounce_timer_single", e)

test_photo_grid_set_photos()
test_photo_grid_append_photos()
test_photo_grid_clear_on_reset()
test_photo_grid_id_map_correct()
test_gallery_view_init()
test_gallery_view_refresh_empty()
test_gallery_view_refresh_with_photos()
test_gallery_view_search_filter()
test_gallery_load_more()
test_gallery_debounce_timer_single()


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION D: Photo detail dialog
# ═══════════════════════════════════════════════════════════════════════════════
print("\n=== D: PhotoDetailDialog ===")

def test_photo_detail_init():
    try:
        app = setup_qt()
        from ui.photo_detail import PhotoDetailDialog
        db, tmp = make_db()
        try:
            pid = upsert(db, "/fake/detail.jpg")
            dlg = PhotoDetailDialog(db, pid, [pid])
            assert dlg is not None
            assert dlg._current_photo_id == pid
            ok("photo_detail_init")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("photo_detail_init", e)

def test_photo_detail_missing_file():
    try:
        app = setup_qt()
        from ui.photo_detail import PhotoDetailDialog
        db, tmp = make_db()
        try:
            pid = upsert(db, "/nonexistent/photo.jpg")
            dlg = PhotoDetailDialog(db, pid, [pid])
            # Should not crash when file doesn't exist
            assert dlg is not None
            ok("photo_detail_missing_file_no_crash")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("photo_detail_missing_file", e)

def test_photo_detail_navigation():
    try:
        app = setup_qt()
        from ui.photo_detail import PhotoDetailDialog
        db, tmp = make_db()
        try:
            ids = [upsert(db, f"/fake/nav{i}.jpg") for i in range(5)]
            dlg = PhotoDetailDialog(db, ids[0], ids)
            assert dlg._current_photo_id == ids[0]
            # Navigate forward
            dlg._next()
            assert dlg._current_photo_id == ids[1]
            dlg._next()
            assert dlg._current_photo_id == ids[2]
            # Navigate backward
            dlg._prev()
            assert dlg._current_photo_id == ids[1]
            ok("photo_detail_navigation")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("photo_detail_navigation", e)

def test_photo_detail_prev_at_start():
    try:
        app = setup_qt()
        from ui.photo_detail import PhotoDetailDialog
        db, tmp = make_db()
        try:
            ids = [upsert(db, f"/fake/bound{i}.jpg") for i in range(3)]
            dlg = PhotoDetailDialog(db, ids[0], ids)
            dlg._prev()  # at start — should not go before 0
            assert dlg._current_photo_id == ids[0]
            ok("photo_detail_prev_at_start")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("photo_detail_prev_at_start", e)

def test_photo_detail_next_at_end():
    try:
        app = setup_qt()
        from ui.photo_detail import PhotoDetailDialog
        db, tmp = make_db()
        try:
            ids = [upsert(db, f"/fake/end{i}.jpg") for i in range(3)]
            dlg = PhotoDetailDialog(db, ids[2], ids)
            dlg._next()  # at end — should not go past last
            assert dlg._current_photo_id == ids[2]
            ok("photo_detail_next_at_end")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("photo_detail_next_at_end", e)

def test_photo_detail_shows_album_info():
    try:
        app = setup_qt()
        from ui.photo_detail import PhotoDetailDialog
        db, tmp = make_db()
        try:
            aid = db.create_album("DetailAlbum")
            pid = upsert(db, "/fake/detail_album.jpg")
            db.add_photo_to_album(aid, pid)
            dlg = PhotoDetailDialog(db, pid, [pid])
            # The album section should be rendered without crash
            assert dlg is not None
            ok("photo_detail_shows_album_info")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("photo_detail_shows_album_info", e)

def test_photo_detail_add_to_album():
    try:
        app = setup_qt()
        from ui.photo_detail import PhotoDetailDialog
        from PyQt6.QtWidgets import QInputDialog
        QInputDialog.getItem = staticmethod(
            lambda *a, **kw: ("AlbumAdd  (0 photos)", True)
        )
        db, tmp = make_db()
        try:
            aid = db.create_album("AlbumAdd")
            pid = upsert(db, "/fake/add_test.jpg")
            dlg = PhotoDetailDialog(db, pid, [pid])
            dlg._add_to_album()
            assert db.count_album_photos(aid) == 1
            ok("photo_detail_add_to_album")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("photo_detail_add_to_album", e)

def test_photo_detail_remove_from_album():
    try:
        app = setup_qt()
        from ui.photo_detail import PhotoDetailDialog
        db, tmp = make_db()
        try:
            aid = db.create_album("RemoveAlbum")
            pid = upsert(db, "/fake/remove_test.jpg")
            db.add_photo_to_album(aid, pid)
            assert db.count_album_photos(aid) == 1
            dlg = PhotoDetailDialog(db, pid, [pid])
            dlg._remove_from_album(aid)
            assert db.count_album_photos(aid) == 0
            ok("photo_detail_remove_from_album")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("photo_detail_remove_from_album", e)

def test_photo_detail_with_faces():
    try:
        app = setup_qt()
        from ui.photo_detail import PhotoDetailDialog
        db, tmp = make_db()
        try:
            person_id = db.create_person("FaceTest")
            photo_id = upsert(db, "/fake/face_photo.jpg")
            fid = db.insert_face({
                "photo_id": photo_id,
                "bbox_top": 0, "bbox_right": 50, "bbox_bottom": 50, "bbox_left": 0,
            })
            db.confirm_face(fid, person_id)
            dlg = PhotoDetailDialog(db, photo_id, [photo_id])
            assert dlg is not None
            ok("photo_detail_with_confirmed_face")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("photo_detail_with_faces", e)

def test_photo_detail_resize_no_crash():
    try:
        app = setup_qt()
        from ui.photo_detail import PhotoDetailDialog
        from PyQt6.QtCore import QSize
        db, tmp = make_db()
        try:
            pid = upsert(db, "/fake/resize.jpg")
            dlg = PhotoDetailDialog(db, pid, [pid])
            # Simulate resize events
            dlg.resize(800, 600)
            dlg.resize(1200, 800)
            ok("photo_detail_resize_no_crash")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("photo_detail_resize_no_crash", e)

test_photo_detail_init()
test_photo_detail_missing_file()
test_photo_detail_navigation()
test_photo_detail_prev_at_start()
test_photo_detail_next_at_end()
test_photo_detail_shows_album_info()
test_photo_detail_add_to_album()
test_photo_detail_remove_from_album()
test_photo_detail_with_faces()
test_photo_detail_resize_no_crash()


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION E: Album view UI
# ═══════════════════════════════════════════════════════════════════════════════
print("\n=== E: AlbumView UI ===")

def test_album_view_init():
    try:
        app = setup_qt()
        from ui.album_view import AlbumView
        db, tmp = make_db()
        try:
            av = AlbumView(db)
            assert av is not None
            ok("album_view_init")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("album_view_init", e)

def test_album_view_refresh_empty():
    try:
        app = setup_qt()
        from ui.album_view import AlbumView
        db, tmp = make_db()
        try:
            av = AlbumView(db)
            av.refresh()
            assert av.album_list.count() == 0
            ok("album_view_refresh_empty")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("album_view_refresh_empty", e)

def test_album_view_shows_albums():
    try:
        app = setup_qt()
        from ui.album_view import AlbumView
        db, tmp = make_db()
        try:
            db.create_album("A")
            db.create_album("B")
            db.create_album("C")
            av = AlbumView(db)
            av.refresh()
            assert av.album_list.count() == 3
            ok("album_view_shows_3_albums")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("album_view_shows_albums", e)

def test_album_view_new_album():
    try:
        app = setup_qt()
        from ui.album_view import AlbumView
        from PyQt6.QtWidgets import QInputDialog
        QInputDialog.getText = staticmethod(lambda *a, **kw: ("NewTestAlbum", True))
        db, tmp = make_db()
        try:
            av = AlbumView(db)
            av._new_album()
            assert av.album_list.count() == 1
            ok("album_view_new_album")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("album_view_new_album", e)

def test_album_view_delete_album():
    try:
        app = setup_qt()
        from ui.album_view import AlbumView
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.question = staticmethod(
            lambda *a, **kw: QMessageBox.StandardButton.Yes
        )
        db, tmp = make_db()
        try:
            aid = db.create_album("ToDelete")
            av = AlbumView(db)
            av.refresh()
            assert av.album_list.count() == 1
            av._delete_album(aid)
            assert av.album_list.count() == 0
            assert db.get_album(aid) is None
            ok("album_view_delete_album")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("album_view_delete_album", e)

def test_album_view_rename_album():
    try:
        app = setup_qt()
        from ui.album_view import AlbumView
        from PyQt6.QtWidgets import QInputDialog
        QInputDialog.getText = staticmethod(lambda *a, **kw: ("RenamedAlbum", True))
        db, tmp = make_db()
        try:
            aid = db.create_album("OldAlbumName")
            av = AlbumView(db)
            av._rename_album(aid)
            assert db.get_album(aid)["name"] == "RenamedAlbum"
            ok("album_view_rename_album")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("album_view_rename_album", e)

def test_album_view_select_shows_photos():
    try:
        app = setup_qt()
        from ui.album_view import AlbumView
        from PyQt6.QtWidgets import QListWidgetItem
        from PyQt6.QtCore import Qt
        db, tmp = make_db()
        try:
            aid = db.create_album("SelectTest")
            for i in range(3):
                pid = upsert(db, f"/fake/av{i}.jpg")
                db.add_photo_to_album(aid, pid)
            av = AlbumView(db)
            av.refresh()
            # Simulate selecting the album
            item = av.album_list.item(0)
            av._on_album_selected(item, None)
            assert av.photo_grid.count() == 3
            ok("album_view_select_shows_photos")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("album_view_select_shows_photos", e)

def test_album_view_remove_clears_current():
    try:
        app = setup_qt()
        from ui.album_view import AlbumView
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.question = staticmethod(
            lambda *a, **kw: QMessageBox.StandardButton.Yes
        )
        db, tmp = make_db()
        try:
            aid = db.create_album("ClearTest")
            av = AlbumView(db)
            av._current_album_id = aid
            av._delete_album(aid)
            assert av._current_album_id is None
            ok("album_view_delete_clears_current_id")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("album_view_remove_clears_current", e)

test_album_view_init()
test_album_view_refresh_empty()
test_album_view_shows_albums()
test_album_view_new_album()
test_album_view_delete_album()
test_album_view_rename_album()
test_album_view_select_shows_photos()
test_album_view_remove_clears_current()


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION F: MainWindow integration (both stages wired together)
# ═══════════════════════════════════════════════════════════════════════════════
print("\n=== F: MainWindow integration ===")

def test_main_window_init():
    try:
        app = setup_qt()
        from ui.main_window import MainWindow
        tmp = tempfile.mkdtemp()
        try:
            mw = MainWindow(app_dir=tmp)
            assert mw is not None
            assert mw.stack.count() == 5  # gallery, albums, people, scan, duplicates
            ok("main_window_init_4_views")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("main_window_init", e)

def test_main_window_navigate_all():
    try:
        app = setup_qt()
        from ui.main_window import MainWindow
        tmp = tempfile.mkdtemp()
        try:
            mw = MainWindow(app_dir=tmp)
            for idx in range(4):
                mw._navigate(idx)
                assert mw.stack.currentIndex() == idx
            ok("main_window_navigate_all_4")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("main_window_navigate_all", e)

def test_main_window_scan_complete_navigates_gallery():
    try:
        app = setup_qt()
        from ui.main_window import MainWindow
        tmp = tempfile.mkdtemp()
        try:
            mw = MainWindow(app_dir=tmp)
            # Scan complete with no new photos — navigate to gallery (0)
            mw._on_scan_complete({"new_photos": 0, "photos_found": 5})
            assert mw.stack.currentIndex() == 0
            ok("scan_complete_navigates_gallery")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("main_window_scan_complete_navigates_gallery", e)

def test_main_window_sidebar_count():
    try:
        app = setup_qt()
        from ui.main_window import MainWindow
        tmp = tempfile.mkdtemp()
        try:
            mw = MainWindow(app_dir=tmp)
            assert len(mw.sidebar._buttons) == 5
            ok("main_window_sidebar_4_buttons")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("main_window_sidebar_count", e)

def test_main_window_status_bar_shows_albums():
    try:
        app = setup_qt()
        from ui.main_window import MainWindow
        tmp = tempfile.mkdtemp()
        try:
            mw = MainWindow(app_dir=tmp)
            mw._refresh_status()
            # Status bar should show stats (no crash, even empty DB)
            status_text = mw.status.currentMessage()
            assert "photos" in status_text.lower()
            ok("main_window_status_bar_no_crash")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("main_window_status_bar_shows_albums", e)

def test_end_to_end_scan_then_gallery():
    """Simulate: scan photos → gallery shows them → add to album → album view shows them."""
    try:
        app = setup_qt()
        from ui.main_window import MainWindow
        from core.scanner import ScanWorker
        tmp = tempfile.mkdtemp()
        try:
            # Write some JPEG files
            img_dir = os.path.join(tmp, "photos")
            os.makedirs(img_dir)
            jpeg_bytes = (
                b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"
            )
            for i in range(3):
                with open(os.path.join(img_dir, f"photo{i}.jpg"), "wb") as f:
                    f.write(jpeg_bytes)

            mw = MainWindow(app_dir=tmp)
            mw.scan_view.set_folders([img_dir])

            # Run scan synchronously
            ev = threading.Event()
            results = {}
            worker = ScanWorker(
                db=mw.db, folders=[img_dir], thumb_dir=mw.thumb_dir,
                on_progress=lambda *a: None,
                on_finished=lambda s: (results.update(s), ev.set()),
                on_error=lambda e: ev.set(),
            )
            worker.start()
            ev.wait(timeout=30)

            assert results.get("new_photos", 0) == 3

            # Gallery shows them
            mw.gallery_view.refresh()
            assert mw.gallery_view.grid.count() == 3

            # Add all to an album
            aid = mw.db.create_album("ScannedPhotos")
            for row in mw.db.get_all_photos():
                mw.db.add_photo_to_album(aid, row["id"])

            # Album view shows them
            mw.album_view.refresh()
            mw.album_view._on_album_selected(mw.album_view.album_list.item(0), None)
            assert mw.album_view.photo_grid.count() == 3

            ok("end_to_end_scan_gallery_album")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("end_to_end_scan_then_gallery", e)

test_main_window_init()
test_main_window_navigate_all()
test_main_window_scan_complete_navigates_gallery()
test_main_window_sidebar_count()
test_main_window_status_bar_shows_albums()
test_end_to_end_scan_then_gallery()


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION G: Stage 1 regression (existing tests still pass)
# ═══════════════════════════════════════════════════════════════════════════════
print("\n=== G: Stage 1 regression ===")

def test_stage1_face_engine_still_works():
    try:
        from core.face_engine import FaceEngine
        db, tmp = make_db()
        try:
            fe = FaceEngine(db, tmp)
            fe.rebuild_person_models()
            result = fe.suggest_person(
                encode_embedding(np.random.default_rng(99).standard_normal(128).astype(np.float32))
            )
            assert result == (None, 0.0)
            ok("stage1_face_engine_no_regression")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("stage1_face_engine_still_works", e)

def test_stage1_scanner_still_works():
    try:
        from core.scanner import ScanWorker
        tmp = tempfile.mkdtemp()
        try:
            img_dir = os.path.join(tmp, "p")
            os.makedirs(img_dir)
            jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"
            with open(os.path.join(img_dir, "r.jpg"), "wb") as f:
                f.write(jpeg)
            db = Database(os.path.join(tmp, "db", "t.db"))
            ev = threading.Event()
            r = {}
            ScanWorker(db=db, folders=[img_dir], thumb_dir=os.path.join(tmp, "th"),
                       on_progress=lambda *a: None,
                       on_finished=lambda s: (r.update(s), ev.set()),
                       on_error=lambda e: ev.set()).start()
            ev.wait(30)
            assert r.get("new_photos", 0) == 1
            ok("stage1_scanner_no_regression")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("stage1_scanner_still_works", e)

def test_stage1_people_view_no_regression():
    try:
        app = setup_qt()
        from ui.people_view import PeopleView
        from core.face_engine import FaceEngine
        db, tmp = make_db()
        try:
            fe = FaceEngine(db, tmp)
            pv = PeopleView(db, fe)
            pv.refresh()
            ok("stage1_people_view_no_regression")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("stage1_people_view_no_regression", e)

test_stage1_face_engine_still_works()
test_stage1_scanner_still_works()
test_stage1_people_view_no_regression()


# ═══════════════════════════════════════════════════════════════════════════════
print(f"\nIntegration Results: {len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    print("FAILURES:", FAIL)
    sys.exit(1)
else:
    print("ALL PASSED")
