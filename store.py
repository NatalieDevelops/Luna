"""
personality/store.py

Local SQLite memory store for interaction history and trust computation.
Separate from the neural unit onboard memory (which has limited capacity).
This store persists all history for long-term trust modeling.
"""

import sqlite3
import time
import logging
import math
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS interactions (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    uid       TEXT NOT NULL,
    valence   REAL NOT NULL,
    ts        REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_uid ON interactions(uid);
"""


class MemoryStore:
    DECAY_HALF_LIFE_DAYS = 30.0   # older interactions have less weight

    def __init__(self, path: str = "data/ruby.db"):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def record_interaction(self, uid: str, valence: float):
        self._conn.execute(
            "INSERT INTO interactions (uid, valence, ts) VALUES (?, ?, ?)",
            (uid, valence, time.time())
        )
        self._conn.commit()

    def get_trust(self, uid: str) -> float:
        """
        Compute trust for a uid as exponentially weighted sum of valences.
        Returns value in [0.0, 1.0].
        """
        rows = self._conn.execute(
            "SELECT valence, ts FROM interactions WHERE uid = ? ORDER BY ts DESC LIMIT 500",
            (uid,)
        ).fetchall()
        if not rows:
            return 0.5   # neutral default for unknown

        now = time.time()
        half_life_s = self.DECAY_HALF_LIFE_DAYS * 86400.0
        weighted_sum = 0.0
        weight_total = 0.0

        for valence, ts in rows:
            age_s = now - ts
            w = math.exp(-math.log(2) * age_s / half_life_s)
            weighted_sum += valence * w
            weight_total += w

        if weight_total == 0.0:
            return 0.5

        raw = weighted_sum / weight_total
        trust = max(0.0, min(1.0, (raw + 1.0) / 2.0))
        return round(trust, 4)

    def get_all_trust(self) -> dict:
        uids = [r[0] for r in self._conn.execute(
            "SELECT DISTINCT uid FROM interactions"
        ).fetchall()]
        return {uid: self.get_trust(uid) for uid in uids}
