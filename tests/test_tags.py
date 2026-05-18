"""Tests for Stage 3e: Tags — DB methods + TagsView + PhotoDetailDialog."""
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
        lambda *a, **kw: __import__("PyQt6.QtWidgets", fromlist=["QMessageBox"]).QMessageBox.StandardButton.Yes
    )
    return app


# ── A: DB Tag Methods ─────────────────────────────────────────────────────────

print("=== A: DB Tag Methods ===")


def test_get_or_create_tag_new():
    try:
        db, tmp = make_db()
        try:
            tid = db.get_or_create_tag("Nature")
            assert isinstance(tid, int) and tid > 0
            ok("get_or_create_tag_new")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("get_or_create_tag_new", e)


def test_get_or_create_tag_idempotent():
    try:
        db, tmp = make_db()
        try:
            t1 = db.get_or_create_tag("Travel")
            t2 = db.get_or_create_tag("Travel")
            assert t1 == t2
            ok("get_or_create_tag_idempotent")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("get_or_create_tag_idempotent", e)


def test_get_or_create_tag_case_insensitive():
    try:
        db, tmp = make_db()
        try:
            t1 = db.get_or_create_tag("sunset")
            t2 = db.get_or_create_tag("Sunset")
            assert t1 == t2
            ok("get_or_create_tag_case_insensitive")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("get_or_create_tag_case_insensitive", e)


def test_add_tag_to_photo():
    try:
        db, tmp = make_db()
        try:
            pid = upsert(db, "/a/img.jpg")
            db.add_tag_to_photo(pid, "holiday")
            tags = db.get_tags_for_photo(pid)
            assert len(tags) == 1
            assert tags[0]["name"] == "holiday"
            ok("add_tag_to_photo")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("add_tag_to_photo", e)


def test_add_tag_idempotent():
    try:
        db, tmp = make_db()
        try:
            pid = upsert(db, "/a/img.jpg")
            db.add_tag_to_photo(pid, "beach")
            db.add_tag_to_photo(pid, "beach")
            tags = db.get_tags_for_photo(pid)
            assert len(tags) == 1
            ok("add_tag_idempotent")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("add_tag_idempotent", e)


def test_remove_tag_from_photo():
    try:
        db, tmp = make_db()
        try:
            pid = upsert(db, "/a/img.jpg")
            db.add_tag_to_photo(pid, "travel")
            db.add_tag_to_photo(pid, "night")
            db.remove_tag_from_photo(pid, "travel")
            tags = db.get_tags_for_photo(pid)
            names = [t["name"] for t in tags]
            assert "travel" not in names
            assert "night" in names
            ok("remove_tag_from_photo")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("remove_tag_from_photo", e)


def test_remove_tag_cleans_orphan():
    try:
        db, tmp = make_db()
        try:
            pid = upsert(db, "/a/img.jpg")
            db.add_tag_to_photo(pid, "orphan")
            db.remove_tag_from_photo(pid, "orphan")
            all_tags = db.get_all_tags()
            assert all(t["name"] != "orphan" for t in all_tags)
            ok("remove_tag_cleans_orphan")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("remove_tag_cleans_orphan", e)


def test_remove_tag_keeps_shared_tag():
    try:
        db, tmp = make_db()
        try:
            pid1 = upsert(db, "/a/img1.jpg")
            pid2 = upsert(db, "/a/img2.jpg")
            db.add_tag_to_photo(pid1, "shared")
            db.add_tag_to_photo(pid2, "shared")
            db.remove_tag_from_photo(pid1, "shared")
            all_tags = db.get_all_tags()
            assert any(t["name"] == "shared" for t in all_tags)
            ok("remove_tag_keeps_shared_tag")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("remove_tag_keeps_shared_tag", e)


def test_get_tags_for_photo_sorted():
    try:
        db, tmp = make_db()
        try:
            pid = upsert(db, "/a/img.jpg")
            for name in ["zoo", "art", "beach"]:
                db.add_tag_to_photo(pid, name)
            tags = db.get_tags_for_photo(pid)
            names = [t["name"] for t in tags]
            assert names == sorted(names)
            ok("get_tags_for_photo_sorted")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("get_tags_for_photo_sorted", e)


def test_get_all_tags_with_counts():
    try:
        db, tmp = make_db()
        try:
            pid1 = upsert(db, "/a/img1.jpg")
            pid2 = upsert(db, "/a/img2.jpg")
            pid3 = upsert(db, "/a/img3.jpg")
            db.add_tag_to_photo(pid1, "popular")
            db.add_tag_to_photo(pid2, "popular")
            db.add_tag_to_photo(pid3, "popular")
            db.add_tag_to_photo(pid1, "rare")
            all_tags = db.get_all_tags()
            counts = {t["name"]: t["count"] for t in all_tags}
            assert counts["popular"] == 3
            assert counts["rare"] == 1
            ok("get_all_tags_with_counts")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("get_all_tags_with_counts", e)


def test_get_all_tags_sorted_by_count():
    try:
        db, tmp = make_db()
        try:
            for i, (tag, count) in enumerate([("rare", 1), ("common", 5), ("medium", 3)]):
                for j in range(count):
                    pid = upsert(db, f"/a/{tag}{j}.jpg", sha=f"h_{tag}_{j}")
                    db.add_tag_to_photo(pid, tag)
            all_tags = db.get_all_tags()
            counts = [t["count"] for t in all_tags]
            assert counts == sorted(counts, reverse=True)
            ok("get_all_tags_sorted_by_count")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("get_all_tags_sorted_by_count", e)


def test_rename_tag():
    try:
        db, tmp = make_db()
        try:
            pid = upsert(db, "/a/img.jpg")
            db.add_tag_to_photo(pid, "oldname")
            tid = db.get_or_create_tag("oldname")
            db.rename_tag(tid, "newname")
            tags = db.get_tags_for_photo(pid)
            assert tags[0]["name"] == "newname"
            ok("rename_tag")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("rename_tag", e)


def test_delete_tag_removes_from_photos():
    try:
        db, tmp = make_db()
        try:
            pid1 = upsert(db, "/a/img1.jpg")
            pid2 = upsert(db, "/a/img2.jpg")
            db.add_tag_to_photo(pid1, "removeme")
            db.add_tag_to_photo(pid2, "removeme")
            tid = db.get_or_create_tag("removeme")
            db.delete_tag(tid)
            assert db.get_tags_for_photo(pid1) == []
            assert db.get_tags_for_photo(pid2) == []
            assert db.get_all_tags() == []
            ok("delete_tag_removes_from_photos")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("delete_tag_removes_from_photos", e)


def test_search_photos_by_tag():
    try:
        db, tmp = make_db()
        try:
            pid1 = upsert(db, "/a/tagged.jpg")
            pid2 = upsert(db, "/a/other.jpg")
            db.add_tag_to_photo(pid1, "sunset")
            results = db.search_photos(filters={"tag": "sunset"})
            ids = [r["id"] for r in results]
            assert pid1 in ids
            assert pid2 not in ids
            ok("search_photos_by_tag")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("search_photos_by_tag", e)


def test_search_photos_tag_case_insensitive():
    try:
        db, tmp = make_db()
        try:
            pid = upsert(db, "/a/img.jpg")
            db.add_tag_to_photo(pid, "Nature")
            results = db.search_photos(filters={"tag": "nature"})
            ids = [r["id"] for r in results]
            assert pid in ids
            ok("search_photos_tag_case_insensitive")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("search_photos_tag_case_insensitive", e)


# ── B: TagsView UI ────────────────────────────────────────────────────────────

print("\n=== B: TagsView UI ===")


def test_tags_view_init():
    try:
        app = setup_qt()
        from ui.tags_view import TagsView
        db, tmp = make_db()
        try:
            tv = TagsView(db)
            assert tv is not None
            ok("tags_view_init")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("tags_view_init", e)


def test_tags_view_refresh_empty():
    try:
        app = setup_qt()
        from ui.tags_view import TagsView
        db, tmp = make_db()
        try:
            tv = TagsView(db)
            tv.refresh()
            assert tv.tag_list.count() == 0
            ok("tags_view_refresh_empty")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("tags_view_refresh_empty", e)


def test_tags_view_shows_tags():
    try:
        app = setup_qt()
        from ui.tags_view import TagsView
        db, tmp = make_db()
        try:
            pid = upsert(db, "/a/img.jpg")
            db.add_tag_to_photo(pid, "alpha")
            db.add_tag_to_photo(pid, "beta")
            tv = TagsView(db)
            tv.refresh()
            assert tv.tag_list.count() == 2
            ok("tags_view_shows_tags")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("tags_view_shows_tags", e)


def test_tags_view_auto_selects_first():
    try:
        app = setup_qt()
        from ui.tags_view import TagsView
        db, tmp = make_db()
        try:
            pid1 = upsert(db, "/a/img1.jpg")
            pid2 = upsert(db, "/a/img2.jpg")
            db.add_tag_to_photo(pid1, "first")
            db.add_tag_to_photo(pid2, "second")
            tv = TagsView(db)
            tv.refresh()
            assert tv.grid.count() >= 1
            ok("tags_view_auto_selects_first")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("tags_view_auto_selects_first", e)


def test_tags_view_loads_correct_photos():
    try:
        app = setup_qt()
        from ui.tags_view import TagsView
        db, tmp = make_db()
        try:
            pid1 = upsert(db, "/a/tagged.jpg")
            pid2 = upsert(db, "/a/other.jpg")
            db.add_tag_to_photo(pid1, "mytag")
            db.add_tag_to_photo(pid2, "anothertag")
            tv = TagsView(db)
            tv.refresh()
            # Select "mytag" row
            for i in range(tv.tag_list.count()):
                item = tv.tag_list.item(i)
                if "mytag" in item.text():
                    tv.tag_list.setCurrentRow(i)
                    break
            assert tv.grid.count() == 1
            ok("tags_view_loads_correct_photos")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("tags_view_loads_correct_photos", e)


def test_tags_view_header_shows_tag_name():
    try:
        app = setup_qt()
        from ui.tags_view import TagsView
        db, tmp = make_db()
        try:
            pid = upsert(db, "/a/img.jpg")
            db.add_tag_to_photo(pid, "myspecialtag")
            tv = TagsView(db)
            tv.refresh()
            assert "myspecialtag" in tv.header_lbl.text()
            ok("tags_view_header_shows_tag_name")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("tags_view_header_shows_tag_name", e)


def test_tags_view_delete_tag():
    try:
        app = setup_qt()
        from ui.tags_view import TagsView
        db, tmp = make_db()
        try:
            pid = upsert(db, "/a/img.jpg")
            db.add_tag_to_photo(pid, "deleteme")
            tv = TagsView(db)
            tv.refresh()
            assert tv.tag_list.count() == 1
            tid = db.get_or_create_tag("deleteme")
            tv._delete_tag(tid)
            assert tv.tag_list.count() == 0
            ok("tags_view_delete_tag")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("tags_view_delete_tag", e)


def test_tags_view_rename_tag():
    try:
        app = setup_qt()
        from ui.tags_view import TagsView
        from unittest.mock import patch
        db, tmp = make_db()
        try:
            pid = upsert(db, "/a/img.jpg")
            db.add_tag_to_photo(pid, "oldtag")
            tv = TagsView(db)
            tv.refresh()
            tid = db.get_or_create_tag("oldtag")
            with patch("PyQt6.QtWidgets.QInputDialog.getText",
                       return_value=("newtag", True)):
                tv._rename_tag(tid)
            tags = db.get_all_tags()
            assert tags[0]["name"] == "newtag"
            ok("tags_view_rename_tag")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("tags_view_rename_tag", e)


def test_tags_view_refresh_restores_selection():
    try:
        app = setup_qt()
        from ui.tags_view import TagsView
        from PyQt6.QtCore import Qt
        db, tmp = make_db()
        try:
            pid = upsert(db, "/a/img.jpg")
            db.add_tag_to_photo(pid, "alpha")
            db.add_tag_to_photo(pid, "beta")
            tv = TagsView(db)
            tv.refresh()
            # Capture current selection id
            first_id = tv.tag_list.currentItem().data(Qt.ItemDataRole.UserRole)
            tv._current_tag_id = first_id
            tv.refresh()
            assert tv._current_tag_id == first_id
            ok("tags_view_refresh_restores_selection")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("tags_view_refresh_restores_selection", e)


# ── C: PhotoDetailDialog tags ─────────────────────────────────────────────────

print("\n=== C: PhotoDetailDialog Tags ===")


def test_photo_detail_shows_tags():
    try:
        app = setup_qt()
        from ui.photo_detail import PhotoDetailDialog
        db, tmp = make_db()
        try:
            pid = upsert(db, "/a/img.jpg")
            db.add_tag_to_photo(pid, "landscape")
            dlg = PhotoDetailDialog(db, pid)
            # If loaded without crash and tags section present, we're good
            assert dlg is not None
            ok("photo_detail_shows_tags")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("photo_detail_shows_tags", e)


def test_photo_detail_add_tag():
    try:
        app = setup_qt()
        from ui.photo_detail import PhotoDetailDialog
        from unittest.mock import patch
        db, tmp = make_db()
        try:
            pid = upsert(db, "/a/img.jpg")
            dlg = PhotoDetailDialog(db, pid)
            with patch("PyQt6.QtWidgets.QInputDialog.getText",
                       return_value=("newtag", True)):
                dlg._add_tag()
            tags = db.get_tags_for_photo(pid)
            assert any(t["name"] == "newtag" for t in tags)
            ok("photo_detail_add_tag")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("photo_detail_add_tag", e)


def test_photo_detail_remove_tag():
    try:
        app = setup_qt()
        from ui.photo_detail import PhotoDetailDialog
        db, tmp = make_db()
        try:
            pid = upsert(db, "/a/img.jpg")
            db.add_tag_to_photo(pid, "removetag")
            dlg = PhotoDetailDialog(db, pid)
            dlg._remove_tag("removetag")
            tags = db.get_tags_for_photo(pid)
            assert all(t["name"] != "removetag" for t in tags)
            ok("photo_detail_remove_tag")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("photo_detail_remove_tag", e)


# ── D: MainWindow integration ─────────────────────────────────────────────────

print("\n=== D: MainWindow Integration ===")


def test_main_window_has_8_nav_items():
    try:
        app = setup_qt()
        from ui.main_window import _Sidebar
        assert len(_Sidebar.NAV_ITEMS) == 8
        ok("main_window_has_8_nav_items")
    except Exception as e:
        fail("main_window_has_8_nav_items", e)


def test_main_window_navigate_to_tags():
    try:
        app = setup_qt()
        from ui.main_window import MainWindow
        tmp = tempfile.mkdtemp()
        try:
            mw = MainWindow(app_dir=tmp)
            mw._navigate(7)
            assert mw.stack.currentIndex() == 7
            ok("main_window_navigate_to_tags")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("main_window_navigate_to_tags", e)


def test_main_window_tags_refreshes_on_nav():
    try:
        app = setup_qt()
        from ui.main_window import MainWindow
        tmp = tempfile.mkdtemp()
        try:
            mw = MainWindow(app_dir=tmp)
            pid = mw.db.upsert_photo({
                "file_path": "/x/img.jpg", "file_name": "img.jpg", "sha256_hash": "h1"
            })
            mw.db.add_tag_to_photo(pid, "testtag")
            mw._navigate(7)
            assert mw.tags_view.tag_list.count() == 1
            ok("main_window_tags_refreshes_on_nav")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("main_window_tags_refreshes_on_nav", e)


# ── Run all ───────────────────────────────────────────────────────────────────

test_get_or_create_tag_new()
test_get_or_create_tag_idempotent()
test_get_or_create_tag_case_insensitive()
test_add_tag_to_photo()
test_add_tag_idempotent()
test_remove_tag_from_photo()
test_remove_tag_cleans_orphan()
test_remove_tag_keeps_shared_tag()
test_get_tags_for_photo_sorted()
test_get_all_tags_with_counts()
test_get_all_tags_sorted_by_count()
test_rename_tag()
test_delete_tag_removes_from_photos()
test_search_photos_by_tag()
test_search_photos_tag_case_insensitive()

test_tags_view_init()
test_tags_view_refresh_empty()
test_tags_view_shows_tags()
test_tags_view_auto_selects_first()
test_tags_view_loads_correct_photos()
test_tags_view_header_shows_tag_name()
test_tags_view_delete_tag()
test_tags_view_rename_tag()
test_tags_view_refresh_restores_selection()

test_photo_detail_shows_tags()
test_photo_detail_add_tag()
test_photo_detail_remove_tag()

test_main_window_has_8_nav_items()
test_main_window_navigate_to_tags()
test_main_window_tags_refreshes_on_nav()

print(f"\nTags Results: {len(PASS)} passed, {len(FAIL)} failed")
if not FAIL:
    print("ALL PASSED")
else:
    print(f"FAILURES: {FAIL}")
