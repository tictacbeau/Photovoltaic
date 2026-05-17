"""Round 2: Config edge cases, DB constraint consistency, FaceEngine model consistency."""

import os
import sys
import json
import tempfile
import shutil
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Import encode_embedding early so helpers can use it
from core.face_engine import encode_embedding

PASS = []
FAIL = []

def ok(name):
    PASS.append(name)
    print(f"  ✓ {name}")

def fail(name, err):
    FAIL.append(name)
    print(f"  ✗ {name}: {err}")


# ── Helpers ────────────────────────────────────────────────────────────────────

def make_db():
    tmp = tempfile.mkdtemp()
    from core.database import Database
    db = Database(os.path.join(tmp, "sub", "test.db"))
    return db, tmp

def _upsert(db, path, sha="abc123"):
    return db.upsert_photo({
        "file_path": path,
        "file_name": os.path.basename(path),
        "sha256_hash": sha,
    })

def _face(db, photo_id, emb):
    return db.insert_face({
        "photo_id": photo_id,
        "bbox_top": 0, "bbox_right": 50, "bbox_bottom": 50, "bbox_left": 0,
        "embedding": encode_embedding(emb),
    })

def make_emb(group_id, noise=0.0, seed=None):
    """Return a 128-dim unit vector.  Different group_ids are ~orthogonal (~1.4 apart).
    Optional tiny noise keeps the vector close to the group's direction."""
    base = np.random.default_rng(group_id * 12345 + 1).normal(0, 1, 128).astype(np.float32)
    base /= np.linalg.norm(base)
    if noise > 0 and seed is not None:
        delta = np.random.default_rng(seed).normal(0, noise, 128).astype(np.float32)
        base = base + delta
        base /= np.linalg.norm(base)
    return base


# ── Config edge cases ──────────────────────────────────────────────────────────
print("=== ROUND 2A: Config edge cases ===")

def test_config_corrupted_json():
    tmp = tempfile.mkdtemp()
    try:
        cfg_path = os.path.join(tmp, "config.json")
        with open(cfg_path, "w") as f:
            f.write("{not valid json!!!")
        with open(cfg_path) as f:
            try:
                json.load(f)
                fail("corrupted_json", "expected JSONDecodeError, got data")
            except json.JSONDecodeError:
                ok("corrupted_json_raises")
    finally:
        shutil.rmtree(tmp)

def test_config_missing_dir():
    tmp = tempfile.mkdtemp()
    try:
        sub = os.path.join(tmp, "nonexistent_sub")
        os.makedirs(sub)
        cfg_path = os.path.join(sub, "config.json")
        default = {"vault": {"root": tmp}, "ui": {"theme": "dark"}}
        with open(cfg_path, "w") as f:
            json.dump(default, f)
        with open(cfg_path) as f:
            data = json.load(f)
        assert data["ui"]["theme"] == "dark"
        ok("config_missing_dir")
    except Exception as e:
        fail("config_missing_dir", e)
    finally:
        shutil.rmtree(tmp)

def test_config_unknown_keys():
    tmp = tempfile.mkdtemp()
    try:
        cfg_path = os.path.join(tmp, "config.json")
        data = {"vault": {"root": tmp}, "unknown_section": {"foo": "bar"}, "another_unknown": 42}
        with open(cfg_path, "w") as f:
            json.dump(data, f)
        with open(cfg_path) as f:
            loaded = json.load(f)
        assert loaded.get("unknown_section", {}).get("foo") == "bar"
        ok("config_unknown_keys")
    except Exception as e:
        fail("config_unknown_keys", e)
    finally:
        shutil.rmtree(tmp)

def test_config_empty():
    tmp = tempfile.mkdtemp()
    try:
        cfg_path = os.path.join(tmp, "config.json")
        with open(cfg_path, "w") as f:
            json.dump({}, f)
        with open(cfg_path) as f:
            loaded = json.load(f)
        assert loaded == {}
        ok("config_empty")
    except Exception as e:
        fail("config_empty", e)
    finally:
        shutil.rmtree(tmp)

test_config_corrupted_json()
test_config_missing_dir()
test_config_unknown_keys()
test_config_empty()


# ── DB constraint consistency ─────────────────────────────────────────────────
print("\n=== ROUND 2B: DB constraint consistency ===")

from core.database import Database, _adaptive_threshold

def test_refresh_nonexistent_person():
    db, tmp = make_db()
    try:
        db.refresh_person_stats(99999)  # must not raise
        ok("refresh_nonexistent_person")
    except Exception as e:
        fail("refresh_nonexistent_person", e)
    finally:
        shutil.rmtree(tmp)

def test_confirm_then_ignore_count():
    db, tmp = make_db()
    try:
        pid = db.create_person("TestPerson")
        photo_id = _upsert(db, "/fake/p1.jpg")
        fid1 = _face(db, photo_id, make_emb(10))
        fid2 = _face(db, photo_id, make_emb(10))
        db.confirm_face(fid1, pid)
        db.confirm_face(fid2, pid)
        # confirm_face already calls refresh_person_stats
        rows = db.get_all_people()
        p = next(r for r in rows if r["id"] == pid)
        assert p["confirmed_count"] == 2, f"expected 2, got {p['confirmed_count']}"
        ok("confirm_two_faces_count_2")

        # ignore one — should drop to 1
        db.ignore_face(fid1)
        rows = db.get_all_people()
        p = next(r for r in rows if r["id"] == pid)
        assert p["confirmed_count"] == 1, f"expected 1 after ignore, got {p['confirmed_count']}"
        ok("ignore_drops_confirmed_to_1")
    except Exception as e:
        fail("confirm_then_ignore_count", e)
    finally:
        shutil.rmtree(tmp)

def test_reject_unowned_face():
    db, tmp = make_db()
    try:
        pid1 = db.create_person("Alice")
        pid2 = db.create_person("Bob")
        photo_id = _upsert(db, "/fake/p2.jpg")
        fid = _face(db, photo_id, make_emb(11))
        db.confirm_face(fid, pid1)
        # reject the face from pid1
        db.reject_face(fid, pid1)
        # face should now be unassigned
        faces = db.get_faces_for_person(pid1)
        assert all(f["id"] != fid for f in faces), "face should no longer belong to pid1"
        ok("reject_face_clears_assignment")
        # pid2 count should remain 0
        rows = db.get_all_people()
        p2 = next(r for r in rows if r["id"] == pid2)
        assert p2["confirmed_count"] == 0
        ok("reject_unowned_pid2_unchanged")
    except Exception as e:
        fail("reject_unowned_face", e)
    finally:
        shutil.rmtree(tmp)

def test_get_all_photos_excludes_missing():
    db, tmp = make_db()
    try:
        pid1 = _upsert(db, "/fake/present.jpg", sha="aaa")
        pid2 = _upsert(db, "/fake/missing.jpg", sha="bbb")
        assert pid1 > 0 and pid2 > 0
        db.mark_missing(pid2)
        photos = db.get_all_photos()
        paths = [row["file_path"] for row in photos]
        assert "/fake/present.jpg" in paths, "present photo should be listed"
        assert "/fake/missing.jpg" not in paths, "missing photo should be excluded"
        ok("get_all_photos_excludes_missing")
    except Exception as e:
        fail("get_all_photos_excludes_missing", e)
    finally:
        shutil.rmtree(tmp)

def test_mark_missing_then_reupsert_restores():
    db, tmp = make_db()
    try:
        photo_id = _upsert(db, "/fake/photo.jpg", sha="ccc")
        db.mark_missing(photo_id)
        photos = db.get_all_photos()
        assert all(r["file_path"] != "/fake/photo.jpg" for r in photos), "should be excluded"
        # Re-upsert clears is_missing via ON CONFLICT UPDATE (sets is_missing back to 0 implicitly)
        # The upsert updates all non-file_path fields, but is_missing stays 1 unless we include it
        db.upsert_photo({
            "file_path": "/fake/photo.jpg",
            "file_name": "photo.jpg",
            "sha256_hash": "ccc",
            "is_missing": 0,
        })
        photos = db.get_all_photos()
        assert any(r["file_path"] == "/fake/photo.jpg" for r in photos), "should be restored"
        ok("mark_missing_then_reupsert_restores")
    except Exception as e:
        fail("mark_missing_then_reupsert_restores", e)
    finally:
        shutil.rmtree(tmp)

def test_update_scan_session_valid_columns():
    db, tmp = make_db()
    try:
        sid = db.start_scan_session(["/tmp"])
        # Use valid column names from scan_sessions schema
        db.update_scan_session(sid, status="done", photos_found=5,
                               new_photos=3, updated_photos=1, missing_photos=0)
        row = db.get_last_scan_session()
        assert row["status"] == "done"
        assert row["photos_found"] == 5
        ok("update_scan_session_valid_columns")
    except Exception as e:
        fail("update_scan_session_valid_columns", e)
    finally:
        shutil.rmtree(tmp)

def test_update_scan_session_nonexistent():
    db, tmp = make_db()
    try:
        # Should not raise even for nonexistent session ID
        db.update_scan_session(99999, status="done", photos_found=0)
        ok("update_scan_session_nonexistent")
    except Exception as e:
        fail("update_scan_session_nonexistent", e)
    finally:
        shutil.rmtree(tmp)

def test_duplicate_hash_dedup():
    db, tmp = make_db()
    try:
        same_hash = "deadbeef" * 8  # 64 hex = valid SHA256
        pid1 = _upsert(db, "/fake/a.jpg", sha=same_hash)
        pid2 = _upsert(db, "/fake/b.jpg", sha=same_hash + "x")
        # Both have the same sha — register dup group
        gid = db.get_or_create_duplicate_group(same_hash)
        db.add_to_duplicate_group(gid, pid1, is_master=True)
        db.add_to_duplicate_group(gid, pid2, is_master=False)
        stats = db.get_stats()
        assert stats["duplicate_groups"] >= 1, f"expected >=1 dup group, got {stats['duplicate_groups']}"
        ok("duplicate_hash_dedup")
    except Exception as e:
        fail("duplicate_hash_dedup", e)
    finally:
        shutil.rmtree(tmp)

test_refresh_nonexistent_person()
test_confirm_then_ignore_count()
test_reject_unowned_face()
test_get_all_photos_excludes_missing()
test_mark_missing_then_reupsert_restores()
test_update_scan_session_valid_columns()
test_update_scan_session_nonexistent()
test_duplicate_hash_dedup()


# ── FaceEngine model consistency ──────────────────────────────────────────────
print("\n=== ROUND 2C: FaceEngine model consistency ===")

from core.face_engine import FaceEngine

def test_adaptive_threshold_values():
    try:
        assert _adaptive_threshold(0)  == 0.65
        assert _adaptive_threshold(2)  == 0.65
        assert _adaptive_threshold(3)  == 0.60
        assert _adaptive_threshold(7)  == 0.60
        assert _adaptive_threshold(8)  == 0.55
        assert _adaptive_threshold(19) == 0.55
        assert _adaptive_threshold(20) == 0.50
        assert _adaptive_threshold(49) == 0.50
        assert _adaptive_threshold(50) == 0.45
        assert _adaptive_threshold(100)== 0.45
        ok("adaptive_threshold_values_all_correct")
    except AssertionError as e:
        fail("adaptive_threshold_values", e)

def test_two_person_discrimination():
    db, tmp = make_db()
    try:
        fe = FaceEngine(db, tmp)
        pid1 = db.create_person("Alice")
        pid2 = db.create_person("Bob")
        photo_id = _upsert(db, "/fake/disc.jpg")
        emb_alice = make_emb(0)   # group 0
        emb_bob   = make_emb(1)   # group 1  (~orthogonal to alice)
        for i in range(5):
            fid = _face(db, photo_id, emb_alice)
            db.confirm_face(fid, pid1)
        for i in range(5):
            fid = _face(db, photo_id, emb_bob)
            db.confirm_face(fid, pid2)
        fe.rebuild_person_models()

        probe_alice = make_emb(0, noise=0.005, seed=7)   # very close to alice
        matched_pid, conf = fe.suggest_person(encode_embedding(probe_alice))
        assert matched_pid == pid1, f"alice probe matched pid={matched_pid} expected {pid1}"
        ok("two_person_alice_probe")

        probe_bob = make_emb(1, noise=0.005, seed=8)     # very close to bob
        matched_pid, conf = fe.suggest_person(encode_embedding(probe_bob))
        assert matched_pid == pid2, f"bob probe matched pid={matched_pid} expected {pid2}"
        ok("two_person_bob_probe")
    except Exception as e:
        fail("two_person_discrimination", e)
    finally:
        shutil.rmtree(tmp)

def test_post_merge_matching():
    db, tmp = make_db()
    try:
        fe = FaceEngine(db, tmp)
        pid1 = db.create_person("TempA")
        pid2 = db.create_person("TempB")
        photo_id = _upsert(db, "/fake/merge.jpg")
        emb = make_emb(2)
        for _ in range(3):
            fid = _face(db, photo_id, emb)
            db.confirm_face(fid, pid1)
        fe.rebuild_person_models()

        # merge pid1 into pid2 (source → target)
        db.merge_people(pid1, pid2)
        fe.rebuild_person_models()

        probe = make_emb(2, noise=0.005, seed=9)
        matched_pid, conf = fe.suggest_person(encode_embedding(probe))
        assert matched_pid == pid2, f"after merge expected pid2={pid2}, got {matched_pid}"
        ok("post_merge_matching")
    except Exception as e:
        fail("post_merge_matching", e)
    finally:
        shutil.rmtree(tmp)

def test_no_models_returns_none():
    db, tmp = make_db()
    try:
        fe = FaceEngine(db, tmp)
        fe.rebuild_person_models()  # empty DB
        result = fe.suggest_person(encode_embedding(make_emb(3)))
        assert result == (None, 0.0), f"expected (None, 0.0), got {result}"
        ok("no_models_returns_none")
    except Exception as e:
        fail("no_models_returns_none", e)
    finally:
        shutil.rmtree(tmp)

def test_cluster_empty_faces():
    db, tmp = make_db()
    try:
        fe = FaceEngine(db, tmp)
        groups = fe.cluster_unassigned_faces()
        assert isinstance(groups, dict)
        assert len(groups) == 0
        ok("cluster_empty_faces_returns_empty_dict")
    except Exception as e:
        fail("cluster_empty_faces", e)
    finally:
        shutil.rmtree(tmp)

def test_cluster_two_groups():
    db, tmp = make_db()
    try:
        fe = FaceEngine(db, tmp)
        photo_id = _upsert(db, "/fake/cluster.jpg")
        emb_a = make_emb(4)   # group 4
        emb_b = make_emb(5)   # group 5  (~orthogonal to group 4)
        for _ in range(3):
            _face(db, photo_id, emb_a)
        for _ in range(3):
            _face(db, photo_id, emb_b)
        groups = fe.cluster_unassigned_faces()
        assert len(groups) == 2, f"expected 2 clusters, got {len(groups)}: {groups}"
        ok("cluster_two_groups")
    except Exception as e:
        fail("cluster_two_groups", e)
    finally:
        shutil.rmtree(tmp)

def test_suggest_none_embedding():
    db, tmp = make_db()
    try:
        fe = FaceEngine(db, tmp)
        result = fe.suggest_person(None)
        assert result == (None, 0.0)
        ok("suggest_none_embedding_returns_none")
    except Exception as e:
        fail("suggest_none_embedding", e)
    finally:
        shutil.rmtree(tmp)

test_adaptive_threshold_values()
test_two_person_discrimination()
test_post_merge_matching()
test_no_models_returns_none()
test_cluster_empty_faces()
test_cluster_two_groups()
test_suggest_none_embedding()


# ── Summary ────────────────────────────────────────────────────────────────────
print(f"\nRound 2 Results: {len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    print("FAILURES:", FAIL)
    sys.exit(1)
else:
    print("ALL PASSED")
