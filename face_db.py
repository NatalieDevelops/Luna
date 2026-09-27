"""
vision/face_db.py

Local face identity store backed by SQLite.
Embeddings are 128-dim float32 vectors from face_recognition.
No cloud calls.
"""

import sqlite3
import numpy as np
import logging
from pathlib import Path
from typing import Tuple

log = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS faces (
    uid       TEXT PRIMARY KEY,
    embedding BLOB NOT NULL,
    enrolled  INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);
"""


class FaceDatabase:
    DISTANCE_THRESHOLD = 0.5   # lower = stricter match

    def __init__(self, path: str = "config/faces.db"):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.execute(SCHEMA)
        self._conn.commit()
        self._cache: dict[str, np.ndarray] = self._load_cache()

    def _load_cache(self) -> dict[str, np.ndarray]:
        cache = {}
        for uid, blob in self._conn.execute("SELECT uid, embedding FROM faces"):
            cache[uid] = np.frombuffer(blob, dtype=np.float32)
        return cache

    def enroll(self, uid: str, embedding: np.ndarray):
        """Store or update a face embedding for a uid."""
        blob = embedding.astype(np.float32).tobytes()
        self._conn.execute(
            "INSERT OR REPLACE INTO faces (uid, embedding) VALUES (?, ?)",
            (uid, blob)
        )
        self._conn.commit()
        self._cache[uid] = embedding.astype(np.float32)
        log.info("enrolled face uid=%s", uid)

    def identify(self, embedding: np.ndarray) -> Tuple[str, float]:
        """
        Find the closest known uid for a given embedding.
        Returns (uid, confidence) where confidence = 1 - distance.
        Returns ("unknown", 0.0) if no match above threshold.
        """
        if not self._cache:
            return ("unknown", 0.0)

        best_uid  = "unknown"
        best_dist = float("inf")

        for uid, known_enc in self._cache.items():
            dist = float(np.linalg.norm(embedding - known_enc))
            if dist < best_dist:
                best_dist = dist
                best_uid  = uid

        if best_dist > self.DISTANCE_THRESHOLD:
            return ("unknown", 0.0)

        confidence = max(0.0, 1.0 - best_dist / self.DISTANCE_THRESHOLD)
        return (best_uid, round(confidence, 4))

    def list_faces(self) -> list[str]:
        return list(self._cache.keys())

    def delete(self, uid: str):
        self._conn.execute("DELETE FROM faces WHERE uid = ?", (uid,))
        self._conn.commit()
        self._cache.pop(uid, None)
        log.info("deleted face uid=%s", uid)
