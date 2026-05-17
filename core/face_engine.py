"""Face detection, embedding, clustering, and adaptive person matching.

The core learning mechanic:
  - Every confirmed face for a person is stored as an embedding (128-d vector).
  - The match distance threshold tightens as more faces are confirmed:
      < 3  confirmed  →  0.65  (loose, catches candidates)
      3-7  confirmed  →  0.60
      8-19 confirmed  →  0.55
      20-49 confirmed →  0.50
      50+  confirmed  →  0.45  (tight, high precision)
  - When matching an unknown face, we compare against the mean embedding of all
    confirmed faces for each person and use that person's current threshold.
  - After the user confirms or rejects suggestions the model gets smarter.
"""

import os
import io
import logging
import threading
import pickle
from typing import Callable

import numpy as np
from PIL import Image

from core.database import Database

log = logging.getLogger(__name__)

try:
    import face_recognition as _fr
    FACE_RECOGNITION_AVAILABLE = True
    log.info("face_recognition library available — facial recognition enabled")
except ImportError:
    FACE_RECOGNITION_AVAILABLE = False
    log.warning(
        "face_recognition library not installed. "
        "Install cmake + dlib + face-recognition to enable facial recognition."
    )


def is_available() -> bool:
    return FACE_RECOGNITION_AVAILABLE


# ── Embedding serialisation ──────────────────────────────────────────────────

def encode_embedding(arr: np.ndarray) -> bytes:
    return pickle.dumps(arr.astype(np.float32))


def decode_embedding(blob: bytes) -> np.ndarray:
    return pickle.loads(blob).astype(np.float64)


# ── Per-person model built from confirmed embeddings ────────────────────────

class PersonModel:
    """Holds the mean embedding and adaptive threshold for one person."""

    __slots__ = ("person_id", "mean_embedding", "threshold", "confirmed_count")

    def __init__(self, person_id: int, embeddings: list[np.ndarray], threshold: float):
        self.person_id = person_id
        self.threshold = threshold
        self.confirmed_count = len(embeddings)
        if embeddings:
            self.mean_embedding = np.mean(embeddings, axis=0)
        else:
            self.mean_embedding = None

    def distance(self, embedding: np.ndarray) -> float:
        if self.mean_embedding is None:
            return float("inf")
        return float(np.linalg.norm(self.mean_embedding - embedding))

    def matches(self, embedding: np.ndarray) -> bool:
        return self.distance(embedding) <= self.threshold


# ── FaceEngine ───────────────────────────────────────────────────────────────

class FaceEngine:
    """Wraps face detection and adaptive person matching."""

    def __init__(self, db: Database, thumb_dir: str, model: str = "hog"):
        self.db = db
        self.thumb_dir = thumb_dir
        self.model = model  # "hog" (fast) or "cnn" (accurate, needs GPU)
        self._lock = threading.Lock()
        self._person_models: dict[int, PersonModel] = {}

    def rebuild_person_models(self):
        """Load all confirmed embeddings from DB and rebuild in-memory models."""
        if not FACE_RECOGNITION_AVAILABLE:
            return
        raw = self.db.get_all_confirmed_embeddings()
        people = {p["id"]: p for p in self.db.get_all_people(include_hidden=True)}
        models = {}
        for pid, blobs in raw.items():
            person = people.get(pid)
            threshold = person["match_threshold"] if person else 0.6
            embeddings = [decode_embedding(b) for b in blobs if b]
            models[pid] = PersonModel(pid, embeddings, threshold)
        with self._lock:
            self._person_models = models
        log.debug("Rebuilt person models for %d people", len(models))

    def detect_faces_in_photo(self, photo_id: int, file_path: str) -> list[dict]:
        """Detect faces in an image file and return a list of face dicts."""
        if not FACE_RECOGNITION_AVAILABLE:
            return []
        if not os.path.exists(file_path):
            return []

        try:
            img = _load_rgb(file_path)
            if img is None:
                return []
            locations = _fr.face_locations(img, model=self.model)
            if not locations:
                return []
            encodings = _fr.face_encodings(img, locations)
        except Exception as exc:
            log.warning("Face detection failed for %s: %s", file_path, exc)
            return []

        results = []
        for (top, right, bottom, left), encoding in zip(locations, encodings):
            thumb = _crop_face_thumbnail(
                file_path, top, right, bottom, left, self.thumb_dir, photo_id
            )
            results.append(
                {
                    "photo_id": photo_id,
                    "bbox_top": top,
                    "bbox_right": right,
                    "bbox_bottom": bottom,
                    "bbox_left": left,
                    "embedding": encode_embedding(encoding),
                    "thumbnail_path": thumb,
                    "confidence": 0.0,
                    "is_confirmed": 0,
                    "is_ignored": 0,
                }
            )
        return results

    def suggest_person(self, embedding_blob: bytes) -> tuple[int | None, float]:
        """Return (person_id, confidence) for the best matching person, or (None, 0)."""
        if not FACE_RECOGNITION_AVAILABLE or embedding_blob is None:
            return None, 0.0

        embedding = decode_embedding(embedding_blob)
        best_pid = None
        best_dist = float("inf")

        with self._lock:
            for pid, model in self._person_models.items():
                dist = model.distance(embedding)
                if dist <= model.threshold and dist < best_dist:
                    best_dist = dist
                    best_pid = pid

        if best_pid is None:
            return None, 0.0
        confidence = max(0.0, 1.0 - best_dist)
        return best_pid, round(confidence, 3)

    def cluster_unassigned_faces(self, distance_threshold: float = 0.55) -> dict[int, list[int]]:
        """Group unassigned face IDs into clusters using single-linkage.

        Returns {cluster_label: [face_id, ...]}  (label -1 = noise/outliers).
        """
        if not FACE_RECOGNITION_AVAILABLE:
            return {}

        rows = self.db.get_unassigned_faces()
        if len(rows) < 2:
            return {0: [r["id"] for r in rows]} if rows else {}

        face_ids = [r["id"] for r in rows]
        embeddings = []
        valid_ids = []
        for row in rows:
            if row["embedding"]:
                try:
                    embeddings.append(decode_embedding(row["embedding"]))
                    valid_ids.append(row["id"])
                except Exception:
                    pass

        if len(embeddings) < 2:
            return {}

        # Build pairwise distance matrix and cluster with DBSCAN
        from scipy.spatial.distance import cdist
        from scipy.cluster.hierarchy import fclusterdata

        arr = np.array(embeddings)
        try:
            labels = fclusterdata(arr, t=distance_threshold, criterion="distance", metric="euclidean")
        except Exception as exc:
            log.warning("Clustering failed: %s", exc)
            return {}

        clusters: dict[int, list[int]] = {}
        for face_id, label in zip(valid_ids, labels):
            clusters.setdefault(int(label), []).append(face_id)
        return clusters

    def auto_assign_cluster(self, face_ids: list[int]) -> int | None:
        """Create (or find) a person for a new cluster. Returns person_id."""
        person_id = self.db.create_person("Unknown Person")
        conn_faces = self.db.get_faces_for_person(person_id)
        # Assign faces without confirming — user must confirm
        db_conn = self.db._conn()
        db_conn.executemany(
            "UPDATE faces SET person_id=? WHERE id=?",
            [(person_id, fid) for fid in face_ids],
        )
        db_conn.commit()
        self.db.refresh_person_stats(person_id)
        return person_id

    def run_face_scan(
        self,
        photo_ids: list[int],
        on_progress: Callable[[int, int], None] = None,
        on_finished: Callable[[int], None] = None,
    ):
        """Background face scan over a list of photo IDs."""
        def _worker():
            total = len(photo_ids)
            face_count = 0
            self.rebuild_person_models()
            for idx, photo_id in enumerate(photo_ids):
                photo = self.db.get_photo(photo_id)
                if not photo or photo["is_missing"]:
                    continue
                # Skip photos already scanned
                existing = self.db.get_faces_for_photo(photo_id)
                if existing:
                    continue
                faces = self.detect_faces_in_photo(photo_id, photo["file_path"])
                for face_data in faces:
                    face_id = self.db.insert_face(face_data)
                    # Try auto-suggest using current person models
                    pid, conf = self.suggest_person(face_data["embedding"])
                    if pid is not None:
                        self.db._conn().execute(
                            "UPDATE faces SET person_id=?, confidence=? WHERE id=?",
                            (pid, conf, face_id),
                        )
                        self.db._conn().commit()
                face_count += len(faces)
                if on_progress:
                    on_progress(idx + 1, total)
            if on_finished:
                on_finished(face_count)

        t = threading.Thread(target=_worker, daemon=True)
        t.start()
        return t


# ── Helpers ──────────────────────────────────────────────────────────────────

def _load_rgb(path: str) -> np.ndarray | None:
    try:
        ext = os.path.splitext(path)[1].lower()
        with Image.open(path) as img:
            img = img.convert("RGB")
            # Resize very large images for speed
            if max(img.size) > 2000:
                img.thumbnail((2000, 2000), Image.LANCZOS)
            return np.array(img)
    except Exception:
        return None


def _crop_face_thumbnail(
    file_path: str,
    top: int, right: int, bottom: int, left: int,
    thumb_dir: str,
    photo_id: int,
    size: int = 128,
) -> str | None:
    try:
        faces_dir = os.path.join(thumb_dir, "faces")
        os.makedirs(faces_dir, exist_ok=True)
        out_path = os.path.join(faces_dir, f"face_{photo_id}_{top}_{left}.jpg")
        if os.path.exists(out_path):
            return out_path
        pad = max(20, (bottom - top) // 4)
        with Image.open(file_path) as img:
            img = img.convert("RGB")
            w, h = img.size
            box = (
                max(0, left - pad),
                max(0, top - pad),
                min(w, right + pad),
                min(h, bottom + pad),
            )
            crop = img.crop(box)
            crop.thumbnail((size, size), Image.LANCZOS)
            crop.save(out_path, "JPEG", quality=90)
        return out_path
    except Exception:
        return None
