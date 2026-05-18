"""Tests for Stage 3d: Export — ExportWorker + ExportDialog."""
import os
import sys
import tempfile
import shutil
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core.database import Database
from core.exporter import ExportWorker

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


def setup_qt():
    from PyQt6.QtWidgets import QApplication, QMessageBox, QFileDialog
    app = QApplication.instance() or QApplication(sys.argv)
    QMessageBox.information = staticmethod(lambda *a, **kw: None)
    QMessageBox.warning = staticmethod(lambda *a, **kw: None)
    QMessageBox.critical = staticmethod(lambda *a, **kw: None)
    QMessageBox.question = staticmethod(
        lambda *a, **kw: __import__("PyQt6.QtWidgets", fromlist=["QMessageBox"]).QMessageBox.StandardButton.Yes
    )
    QFileDialog.getExistingDirectory = staticmethod(lambda *a, **kw: "")
    return app


def make_photo_files(tmp, names):
    """Create real files and return their paths."""
    paths = []
    for name in names:
        p = os.path.join(tmp, name)
        with open(p, "wb") as f:
            f.write(b"fake image data " + name.encode())
        paths.append(p)
    return paths


# ── A: ExportWorker ───────────────────────────────────────────────────────────

print("=== A: ExportWorker ===")


def test_export_copies_files():
    try:
        tmp = tempfile.mkdtemp()
        try:
            src_dir = os.path.join(tmp, "src")
            dst_dir = os.path.join(tmp, "dst")
            os.makedirs(src_dir)
            paths = make_photo_files(src_dir, ["a.jpg", "b.jpg", "c.jpg"])
            photos = [{"file_path": p, "exif_date": None, "date_added": "2023-01-01"} for p in paths]
            done_stats = {}

            def on_done(s):
                done_stats.update(s)

            w = ExportWorker(photos, dst_dir, on_done=on_done)
            w.start()
            w.join(timeout=5)
            assert done_stats["copied"] == 3
            assert done_stats["skipped"] == 0
            assert done_stats["errors"] == 0
            for name in ["a.jpg", "b.jpg", "c.jpg"]:
                assert os.path.exists(os.path.join(dst_dir, name))
            ok("export_copies_files")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("export_copies_files", e)


def test_export_skips_missing_files():
    try:
        tmp = tempfile.mkdtemp()
        try:
            dst_dir = os.path.join(tmp, "dst")
            photos = [
                {"file_path": "/nonexistent/ghost.jpg", "exif_date": None, "date_added": "2023-01-01"},
            ]
            done_stats = {}
            w = ExportWorker(photos, dst_dir, on_done=lambda s: done_stats.update(s))
            w.start()
            w.join(timeout=5)
            assert done_stats["skipped"] == 1
            assert done_stats["copied"] == 0
            ok("export_skips_missing_files")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("export_skips_missing_files", e)


def test_export_rename_date():
    try:
        tmp = tempfile.mkdtemp()
        try:
            src_dir = os.path.join(tmp, "src")
            dst_dir = os.path.join(tmp, "dst")
            os.makedirs(src_dir)
            paths = make_photo_files(src_dir, ["shot.jpg"])
            photos = [{"file_path": paths[0], "exif_date": "2023-08-15 14:30:00", "date_added": ""}]
            w = ExportWorker(photos, dst_dir, rename_mode="date")
            w.start()
            w.join(timeout=5)
            files = os.listdir(dst_dir)
            assert len(files) == 1
            assert files[0].startswith("20230815_143000_")
            ok("export_rename_date")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("export_rename_date", e)


def test_export_rename_sequence():
    try:
        tmp = tempfile.mkdtemp()
        try:
            src_dir = os.path.join(tmp, "src")
            dst_dir = os.path.join(tmp, "dst")
            os.makedirs(src_dir)
            paths = make_photo_files(src_dir, ["x.jpg", "y.jpg"])
            photos = [{"file_path": p, "exif_date": None, "date_added": "2023-01-01"} for p in paths]
            w = ExportWorker(photos, dst_dir, rename_mode="sequence")
            w.start()
            w.join(timeout=5)
            files = sorted(os.listdir(dst_dir))
            assert files[0].startswith("0001_")
            assert files[1].startswith("0002_")
            ok("export_rename_sequence")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("export_rename_sequence", e)


def test_export_collision_resolved():
    try:
        tmp = tempfile.mkdtemp()
        try:
            src_dir = os.path.join(tmp, "src")
            dst_dir = os.path.join(tmp, "dst")
            os.makedirs(src_dir)
            os.makedirs(dst_dir)
            # Pre-place "photo.jpg" in dst
            with open(os.path.join(dst_dir, "photo.jpg"), "wb") as f:
                f.write(b"existing")
            paths = make_photo_files(src_dir, ["photo.jpg"])
            photos = [{"file_path": paths[0], "exif_date": None, "date_added": "2023-01-01"}]
            w = ExportWorker(photos, dst_dir)
            w.start()
            w.join(timeout=5)
            # Should create photo_1.jpg
            assert os.path.exists(os.path.join(dst_dir, "photo_1.jpg"))
            ok("export_collision_resolved")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("export_collision_resolved", e)


def test_export_stop_mid_run():
    try:
        tmp = tempfile.mkdtemp()
        try:
            src_dir = os.path.join(tmp, "src")
            dst_dir = os.path.join(tmp, "dst")
            os.makedirs(src_dir)
            paths = make_photo_files(src_dir, [f"f{i:03d}.jpg" for i in range(50)])
            photos = [{"file_path": p, "exif_date": None, "date_added": "2023-01-01"} for p in paths]
            w = ExportWorker(photos, dst_dir)
            w.start()
            w.stop()
            w.join(timeout=5)
            # Fewer than 50 files should be copied
            copied = len(os.listdir(dst_dir))
            assert copied < 50
            ok("export_stop_mid_run")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("export_stop_mid_run", e)


def test_export_progress_callback():
    try:
        tmp = tempfile.mkdtemp()
        try:
            src_dir = os.path.join(tmp, "src")
            dst_dir = os.path.join(tmp, "dst")
            os.makedirs(src_dir)
            paths = make_photo_files(src_dir, ["a.jpg", "b.jpg"])
            photos = [{"file_path": p, "exif_date": None, "date_added": "2023-01-01"} for p in paths]
            calls = []
            w = ExportWorker(photos, dst_dir, on_progress=lambda c, t, f: calls.append(c))
            w.start()
            w.join(timeout=5)
            assert len(calls) == 2
            assert calls[-1] == 2
            ok("export_progress_callback")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("export_progress_callback", e)


def test_export_creates_dest_dir():
    try:
        tmp = tempfile.mkdtemp()
        try:
            src_dir = os.path.join(tmp, "src")
            dst_dir = os.path.join(tmp, "new_subdir", "deep")
            os.makedirs(src_dir)
            paths = make_photo_files(src_dir, ["img.jpg"])
            photos = [{"file_path": paths[0], "exif_date": None, "date_added": "2023-01-01"}]
            w = ExportWorker(photos, dst_dir)
            w.start()
            w.join(timeout=5)
            assert os.path.isdir(dst_dir)
            ok("export_creates_dest_dir")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("export_creates_dest_dir", e)


def test_export_date_fallback_to_date_added():
    try:
        tmp = tempfile.mkdtemp()
        try:
            src_dir = os.path.join(tmp, "src")
            dst_dir = os.path.join(tmp, "dst")
            os.makedirs(src_dir)
            paths = make_photo_files(src_dir, ["noexif.jpg"])
            photos = [{"file_path": paths[0], "exif_date": None, "date_added": "2021-05-20 08:00:00"}]
            w = ExportWorker(photos, dst_dir, rename_mode="date")
            w.start()
            w.join(timeout=5)
            files = os.listdir(dst_dir)
            assert files[0].startswith("20210520_")
            ok("export_date_fallback_to_date_added")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("export_date_fallback_to_date_added", e)


# ── B: ExportDialog UI ────────────────────────────────────────────────────────

print("\n=== B: ExportDialog UI ===")


def test_export_dialog_init():
    try:
        app = setup_qt()
        from ui.export_dialog import ExportDialog
        db, tmp = make_db()
        try:
            dlg = ExportDialog(db)
            assert dlg is not None
            ok("export_dialog_init")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("export_dialog_init", e)


def test_export_dialog_lists_albums():
    try:
        app = setup_qt()
        from ui.export_dialog import ExportDialog
        db, tmp = make_db()
        try:
            db.create_album("Vacation")
            db.create_album("Wedding")
            db.ensure_builtin_smart_albums()
            dlg = ExportDialog(db)
            texts = [dlg.src_combo.itemText(i) for i in range(dlg.src_combo.count())]
            assert any("Vacation" in t for t in texts)
            assert any("Wedding" in t for t in texts)
            ok("export_dialog_lists_albums")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("export_dialog_lists_albums", e)


def test_export_dialog_lists_smart_albums():
    try:
        app = setup_qt()
        from ui.export_dialog import ExportDialog
        db, tmp = make_db()
        try:
            db.ensure_builtin_smart_albums()
            dlg = ExportDialog(db)
            texts = [dlg.src_combo.itemText(i) for i in range(dlg.src_combo.count())]
            assert any("This Month" in t for t in texts)
            ok("export_dialog_lists_smart_albums")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("export_dialog_lists_smart_albums", e)


def test_export_dialog_no_dest_shows_warning():
    try:
        app = setup_qt()
        from ui.export_dialog import ExportDialog
        from unittest.mock import patch
        db, tmp = make_db()
        try:
            db.create_album("A")
            dlg = ExportDialog(db)
            dlg.dest_edit.setText("")
            warned = []
            with patch("PyQt6.QtWidgets.QMessageBox.warning",
                       side_effect=lambda *a, **kw: warned.append(True)):
                dlg._start_export()
            assert len(warned) == 1
            ok("export_dialog_no_dest_shows_warning")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("export_dialog_no_dest_shows_warning", e)


def test_export_dialog_rename_mode_selection():
    try:
        app = setup_qt()
        from ui.export_dialog import ExportDialog
        db, tmp = make_db()
        try:
            dlg = ExportDialog(db)
            # Default is "original"
            assert dlg._get_rename_mode() == "original"
            # Select second button (date)
            btns = dlg._rename_group.buttons()
            for b in btns:
                if b.property("rename_mode") == "date":
                    b.setChecked(True)
            assert dlg._get_rename_mode() == "date"
            ok("export_dialog_rename_mode_selection")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("export_dialog_rename_mode_selection", e)


def test_export_dialog_photo_count_updates():
    try:
        app = setup_qt()
        from ui.export_dialog import ExportDialog
        db, tmp = make_db()
        try:
            aid = db.create_album("MyAlbum")
            for i in range(3):
                pid = db.upsert_photo({
                    "file_path": f"/x/p{i}.jpg", "file_name": f"p{i}.jpg",
                    "sha256_hash": f"h{i}",
                })
                db.add_photo_to_album(aid, pid)
            dlg = ExportDialog(db)
            # Select the album (first combo item)
            dlg.src_combo.setCurrentIndex(0)
            dlg._on_source_changed()
            assert "3" in dlg.photo_count_lbl.text()
            ok("export_dialog_photo_count_updates")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("export_dialog_photo_count_updates", e)


# ── C: MainWindow export button ───────────────────────────────────────────────

print("\n=== C: MainWindow Export Button ===")


def test_main_window_has_export_button():
    try:
        app = setup_qt()
        from ui.main_window import MainWindow
        tmp = tempfile.mkdtemp()
        try:
            mw = MainWindow(app_dir=tmp)
            assert hasattr(mw, "_export_btn")
            assert mw._export_btn is not None
            ok("main_window_has_export_button")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("main_window_has_export_button", e)


def test_main_window_open_export_no_crash():
    try:
        app = setup_qt()
        from ui.main_window import MainWindow
        from unittest.mock import patch
        tmp = tempfile.mkdtemp()
        try:
            mw = MainWindow(app_dir=tmp)
            # Patch exec to not block
            with patch("ui.export_dialog.ExportDialog.exec", return_value=0):
                mw._open_export()
            ok("main_window_open_export_no_crash")
        finally:
            shutil.rmtree(tmp)
    except Exception as e:
        fail("main_window_open_export_no_crash", e)


# ── Run all ───────────────────────────────────────────────────────────────────

test_export_copies_files()
test_export_skips_missing_files()
test_export_rename_date()
test_export_rename_sequence()
test_export_collision_resolved()
test_export_stop_mid_run()
test_export_progress_callback()
test_export_creates_dest_dir()
test_export_date_fallback_to_date_added()

test_export_dialog_init()
test_export_dialog_lists_albums()
test_export_dialog_lists_smart_albums()
test_export_dialog_no_dest_shows_warning()
test_export_dialog_rename_mode_selection()
test_export_dialog_photo_count_updates()

test_main_window_has_export_button()
test_main_window_open_export_no_crash()

print(f"\nExport Results: {len(PASS)} passed, {len(FAIL)} failed")
if not FAIL:
    print("ALL PASSED")
else:
    print(f"FAILURES: {FAIL}")
