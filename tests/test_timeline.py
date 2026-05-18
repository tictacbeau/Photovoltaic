"""Tests for Stage 3b: Timeline View — DB methods + UI."""
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


def upsert(db, path, exif_date=None, sha=None):
    data = {
        "file_path": path,
        "file_name": os.path.basename(path),
        "sha256_hash": sha or ("hash_" + os.path.basename(path)),
    }
    if exif_date:
        data["exif_date"] = exif_date
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


# ── A: DB Timeline Methods ────────────────────────────────────────────────────

print("=== A: DB Timeline Methods ===")


def test_get_timeline_months_empty():
    try:
        db, tmp = make_db()
        try:
            result = db.get_timeline_months()
            assert result == []
            ok("get_timeline_months_empty")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("get_timeline_months_empty", e)


def test_get_timeline_months_groups_by_month():
    try:
        db, tmp = make_db()
        try:
            upsert(db, "/a/jan1.jpg", "2023-01-10 12:00:00")
            upsert(db, "/a/jan2.jpg", "2023-01-20 12:00:00")
            upsert(db, "/a/feb1.jpg", "2023-02-05 12:00:00")
            upsert(db, "/a/dec1.jpg", "2022-12-01 12:00:00")
            months = db.get_timeline_months()
            assert len(months) == 3
            yms = [m["year_month"] for m in months]
            assert "2023-01" in yms
            assert "2023-02" in yms
            assert "2022-12" in yms
            ok("get_timeline_months_groups_by_month")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("get_timeline_months_groups_by_month", e)


def test_get_timeline_months_sorted_newest_first():
    try:
        db, tmp = make_db()
        try:
            upsert(db, "/a/old.jpg", "2020-06-01 00:00:00")
            upsert(db, "/a/mid.jpg", "2022-03-15 00:00:00")
            upsert(db, "/a/new.jpg", "2024-11-01 00:00:00")
            months = db.get_timeline_months()
            yms = [m["year_month"] for m in months]
            assert yms == ["2024-11", "2022-03", "2020-06"]
            ok("get_timeline_months_sorted_newest_first")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("get_timeline_months_sorted_newest_first", e)


def test_get_timeline_months_counts():
    try:
        db, tmp = make_db()
        try:
            for i in range(5):
                upsert(db, f"/a/jan{i}.jpg", "2023-01-01 00:00:00", sha=f"h{i}")
            upsert(db, "/a/feb1.jpg", "2023-02-01 00:00:00")
            months = db.get_timeline_months()
            counts = {m["year_month"]: m["count"] for m in months}
            assert counts["2023-01"] == 5
            assert counts["2023-02"] == 1
            ok("get_timeline_months_counts")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("get_timeline_months_counts", e)


def test_get_timeline_months_falls_back_to_date_added():
    try:
        db, tmp = make_db()
        try:
            # No exif_date — should use date_added (which is CURRENT_TIMESTAMP)
            upsert(db, "/a/no_exif.jpg")
            months = db.get_timeline_months()
            # Should still return 1 month entry (current month)
            assert len(months) == 1
            ok("get_timeline_months_falls_back_to_date_added")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("get_timeline_months_falls_back_to_date_added", e)


def test_get_timeline_months_excludes_missing():
    try:
        db, tmp = make_db()
        try:
            pid = upsert(db, "/a/gone.jpg", "2023-05-01 00:00:00")
            upsert(db, "/a/here.jpg", "2023-06-01 00:00:00")
            db.mark_missing(pid)
            months = db.get_timeline_months()
            yms = [m["year_month"] for m in months]
            assert "2023-05" not in yms
            assert "2023-06" in yms
            ok("get_timeline_months_excludes_missing")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("get_timeline_months_excludes_missing", e)


def test_get_photos_for_month():
    try:
        db, tmp = make_db()
        try:
            pid1 = upsert(db, "/a/jan1.jpg", "2023-01-10 09:00:00")
            pid2 = upsert(db, "/a/jan2.jpg", "2023-01-25 18:00:00")
            upsert(db, "/a/feb1.jpg", "2023-02-01 00:00:00")
            photos = db.get_photos_for_month(2023, 1)
            ids = [p["id"] for p in photos]
            assert pid1 in ids
            assert pid2 in ids
            assert len(photos) == 2
            ok("get_photos_for_month")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("get_photos_for_month", e)


def test_get_photos_for_month_sorted_ascending():
    try:
        db, tmp = make_db()
        try:
            pid_late = upsert(db, "/a/late.jpg", "2023-03-28 23:00:00")
            pid_early = upsert(db, "/a/early.jpg", "2023-03-01 06:00:00")
            photos = db.get_photos_for_month(2023, 3)
            assert photos[0]["id"] == pid_early
            assert photos[1]["id"] == pid_late
            ok("get_photos_for_month_sorted_ascending")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("get_photos_for_month_sorted_ascending", e)


def test_get_photos_for_month_empty():
    try:
        db, tmp = make_db()
        try:
            upsert(db, "/a/jan.jpg", "2023-01-01 00:00:00")
            photos = db.get_photos_for_month(2023, 7)
            assert photos == []
            ok("get_photos_for_month_empty")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("get_photos_for_month_empty", e)


# ── B: TimelineView UI ────────────────────────────────────────────────────────

print("\n=== B: TimelineView UI ===")


def test_timeline_view_init():
    try:
        app = setup_qt()
        from ui.timeline_view import TimelineView
        db, tmp = make_db()
        try:
            tv = TimelineView(db)
            assert tv is not None
            ok("timeline_view_init")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("timeline_view_init", e)


def test_timeline_view_refresh_empty():
    try:
        app = setup_qt()
        from ui.timeline_view import TimelineView
        db, tmp = make_db()
        try:
            tv = TimelineView(db)
            tv.refresh()
            assert tv.month_list.count() == 0
            ok("timeline_view_refresh_empty")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("timeline_view_refresh_empty", e)


def test_timeline_view_shows_months():
    try:
        app = setup_qt()
        from ui.timeline_view import TimelineView
        db, tmp = make_db()
        try:
            upsert(db, "/a/jan.jpg", "2023-01-01 00:00:00")
            upsert(db, "/a/feb.jpg", "2023-02-01 00:00:00")
            tv = TimelineView(db)
            tv.refresh()
            # Items include year-separator + 2 month rows = 3 items
            assert tv.month_list.count() == 3
            ok("timeline_view_shows_months")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("timeline_view_shows_months", e)


def test_timeline_view_year_separators():
    try:
        app = setup_qt()
        from ui.timeline_view import TimelineView
        from PyQt6.QtCore import Qt
        db, tmp = make_db()
        try:
            upsert(db, "/a/2022.jpg", "2022-06-01 00:00:00")
            upsert(db, "/a/2023.jpg", "2023-03-01 00:00:00")
            tv = TimelineView(db)
            tv.refresh()
            # 2 year separators + 2 month rows = 4 items
            assert tv.month_list.count() == 4
            # Year separator items have UserRole=None and are not selectable
            sep_items = [
                tv.month_list.item(i)
                for i in range(tv.month_list.count())
                if tv.month_list.item(i).data(Qt.ItemDataRole.UserRole) is None
            ]
            assert len(sep_items) == 2
            ok("timeline_view_year_separators")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("timeline_view_year_separators", e)


def test_timeline_view_auto_selects_first_month():
    try:
        app = setup_qt()
        from ui.timeline_view import TimelineView
        db, tmp = make_db()
        try:
            upsert(db, "/a/new.jpg", "2024-05-01 00:00:00")
            upsert(db, "/a/old.jpg", "2020-01-01 00:00:00")
            tv = TimelineView(db)
            tv.refresh()
            # Should auto-load the newest month into grid
            assert tv.grid.count() == 1
            assert tv._current_ym == "2024-05"
            ok("timeline_view_auto_selects_first_month")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("timeline_view_auto_selects_first_month", e)


def test_timeline_view_grid_loads_correct_photos():
    try:
        app = setup_qt()
        from ui.timeline_view import TimelineView
        from PyQt6.QtCore import Qt
        db, tmp = make_db()
        try:
            upsert(db, "/a/mar1.jpg", "2023-03-10 00:00:00")
            upsert(db, "/a/mar2.jpg", "2023-03-20 00:00:00")
            upsert(db, "/a/apr1.jpg", "2023-04-01 00:00:00")
            tv = TimelineView(db)
            tv.refresh()
            # First month (newest = April) should be loaded with 1 photo
            assert tv.grid.count() == 1
            # Manually select March
            tv._load_month("2023-03")
            assert tv.grid.count() == 2
            ok("timeline_view_grid_loads_correct_photos")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("timeline_view_grid_loads_correct_photos", e)


def test_timeline_view_month_header_text():
    try:
        app = setup_qt()
        from ui.timeline_view import TimelineView
        db, tmp = make_db()
        try:
            upsert(db, "/a/aug.jpg", "2021-08-15 00:00:00")
            tv = TimelineView(db)
            tv.refresh()
            assert "August" in tv.month_header.text()
            assert "2021" in tv.month_header.text()
            ok("timeline_view_month_header_text")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("timeline_view_month_header_text", e)


def test_timeline_view_count_label():
    try:
        app = setup_qt()
        from ui.timeline_view import TimelineView
        db, tmp = make_db()
        try:
            for i in range(4):
                upsert(db, f"/a/p{i}.jpg", "2023-07-01 00:00:00", sha=f"h{i}")
            tv = TimelineView(db)
            tv.refresh()
            assert "4" in tv.count_label.text()
            ok("timeline_view_count_label")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("timeline_view_count_label", e)


def test_timeline_view_refresh_restores_selection():
    try:
        app = setup_qt()
        from ui.timeline_view import TimelineView
        db, tmp = make_db()
        try:
            upsert(db, "/a/jan.jpg", "2023-01-01 00:00:00")
            upsert(db, "/a/jun.jpg", "2023-06-01 00:00:00")
            tv = TimelineView(db)
            tv.refresh()
            # Manually set current to January
            tv._current_ym = "2023-01"
            tv.refresh()
            # After refresh, January should still be selected
            assert tv._current_ym == "2023-01"
            ok("timeline_view_refresh_restores_selection")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("timeline_view_refresh_restores_selection", e)


# ── C: MainWindow integration ─────────────────────────────────────────────────

print("\n=== C: MainWindow Integration ===")


def test_main_window_has_6_nav_items():
    try:
        app = setup_qt()
        from ui.main_window import _Sidebar
        assert len(_Sidebar.NAV_ITEMS) == 8
        ok("main_window_has_6_nav_items")
    except Exception as e:
        fail("main_window_has_6_nav_items", e)


def test_main_window_navigate_to_timeline():
    try:
        app = setup_qt()
        from ui.main_window import MainWindow
        tmp = tempfile.mkdtemp()
        try:
            mw = MainWindow(app_dir=tmp)
            mw._navigate(5)
            assert mw.stack.currentIndex() == 5
            ok("main_window_navigate_to_timeline")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("main_window_navigate_to_timeline", e)


def test_main_window_timeline_refreshes_on_nav():
    try:
        app = setup_qt()
        from ui.main_window import MainWindow
        tmp = tempfile.mkdtemp()
        try:
            mw = MainWindow(app_dir=tmp)
            mw.db.upsert_photo({
                "file_path": "/x/img.jpg", "file_name": "img.jpg",
                "sha256_hash": "h1", "exif_date": "2023-09-01 12:00:00",
            })
            mw._navigate(5)
            assert mw.timeline_view.month_list.count() > 0
            ok("main_window_timeline_refreshes_on_nav")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("main_window_timeline_refreshes_on_nav", e)


# ── Run all ───────────────────────────────────────────────────────────────────

test_get_timeline_months_empty()
test_get_timeline_months_groups_by_month()
test_get_timeline_months_sorted_newest_first()
test_get_timeline_months_counts()
test_get_timeline_months_falls_back_to_date_added()
test_get_timeline_months_excludes_missing()
test_get_photos_for_month()
test_get_photos_for_month_sorted_ascending()
test_get_photos_for_month_empty()

test_timeline_view_init()
test_timeline_view_refresh_empty()
test_timeline_view_shows_months()
test_timeline_view_year_separators()
test_timeline_view_auto_selects_first_month()
test_timeline_view_grid_loads_correct_photos()
test_timeline_view_month_header_text()
test_timeline_view_count_label()
test_timeline_view_refresh_restores_selection()

test_main_window_has_6_nav_items()
test_main_window_navigate_to_timeline()
test_main_window_timeline_refreshes_on_nav()

print(f"\nTimeline Results: {len(PASS)} passed, {len(FAIL)} failed")
if not FAIL:
    print("ALL PASSED")
else:
    print(f"FAILURES: {FAIL}")
