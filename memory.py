"""
firmware/memory.py

Episodic + semantic memory interface to the neural unit.
The unit maintains a rolling episodic buffer (last 2048 events)
and a compact semantic trust map keyed by uid hash.
"""

from __future__ import annotations
import hashlib
import logging
import struct
import time
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .neural_unit import NeuralUnit

log = logging.getLogger(__name__)

# CMD IDs
CMD_ENCODE   = 0x30
CMD_RECALL   = 0x31
CMD_TRUST    = 0x32
CMD_MEM_WIPE = 0x3F

EVENT_NAMES = {
    "pet_detected", "face_seen", "object_seen", "touch_head",
    "touch_back", "touch_chin", "touch_paw", "tail_grab",
    "loud_noise", "darkness", "picked_up", "put_down",
    "fed", "play_initiated", "ignored",
}


class MemoryStore:
    def __init__(self, unit: NeuralUnit):
        self._unit = unit

    @staticmethod
    def _hash_uid(uid: str) -> bytes:
        return hashlib.sha256(uid.encode()).digest()[:8]

    def encode(self, event: str, uid: str, valence: float, timestamp: Optional[float] = None):
        """
        Write an episodic event to the neural unit memory buffer.
        valence: -1.0 (very negative) .. +1.0 (very positive)
        """
        if event not in EVENT_NAMES:
            raise ValueError(f"unknown event: {event!r}. valid: {EVENT_NAMES}")
        ts = int(timestamp or time.time())
        ev_bytes = event.encode("ascii").ljust(24, b"\x00")[:24]
        uid_hash = self._hash_uid(uid)
        val_i16  = int((valence + 1.0) / 2.0 * 65535).to_bytes(2, "big")
        ts_bytes = ts.to_bytes(4, "big")
        payload  = ev_bytes + uid_hash + val_i16 + ts_bytes
        self._unit.send_cmd(CMD_ENCODE, payload)
        log.debug("memory.encode event=%s uid=%s valence=%.2f", event, uid, valence)

    def recall(self, limit: int = 16) -> list[dict]:
        """Return last N episodic events from onboard buffer."""
        payload = limit.to_bytes(2, "big")
        raw = self._unit.send_cmd(CMD_RECALL, payload)
        events = []
        record_size = 38  # 24 + 8 + 2 + 4
        for i in range(0, len(raw), record_size):
            chunk = raw[i:i+record_size]
            if len(chunk) < record_size:
                break
            name    = chunk[:24].rstrip(b"\x00").decode("ascii", errors="replace")
            valence = (int.from_bytes(chunk[32:34], "big") / 65535.0) * 2.0 - 1.0
            ts      = int.from_bytes(chunk[34:38], "big")
            events.append({"event": name, "valence": round(valence, 4), "ts": ts})
        return events

    def get_trust(self, uid: str) -> float:
        """
        Return trust level for a uid (0.0 = unknown/hostile, 1.0 = fully trusted).
        Trust is derived from interaction history held in semantic memory.
        """
        uid_hash = self._hash_uid(uid)
        raw = self._unit.send_cmd(CMD_TRUST, uid_hash)
        if len(raw) < 2:
            return 0.0
        return int.from_bytes(raw[:2], "big") / 65535.0

    def wipe(self):
        """Destructively clear all episodic and semantic memory."""
        log.warning("wiping all neural unit memory")
        self._unit.send_cmd(CMD_MEM_WIPE, b"\xDE\xAD")
