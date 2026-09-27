"""
firmware/personality.py

Personality trait interface. Traits are floats in [0,1] stored in
onboard flash. They drift slowly over time based on interaction events
encoded into memory. Snapshot/restore is supported for backup.
"""

from __future__ import annotations
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .neural_unit import NeuralUnit

log = logging.getLogger(__name__)

CMD_TRAIT_GET      = 0x40
CMD_TRAIT_SET      = 0x41
CMD_TRAIT_SNAPSHOT = 0x42
CMD_TRAIT_RESET    = 0x4F

DEFAULT_TRAITS = {
    "bold":          0.5,
    "playful":       0.6,
    "cautious":      0.5,
    "affectionate":  0.6,
    "vocal":         0.5,
    "independent":   0.4,
}


class PersonalityEngine:
    def __init__(self, unit: NeuralUnit):
        self._unit = unit

    def get(self, trait: str) -> float:
        t = trait.encode("ascii").ljust(16, b"\x00")[:16]
        raw = self._unit.send_cmd(CMD_TRAIT_GET, t)
        return int.from_bytes(raw[:2], "big") / 65535.0

    def set(self, trait: str, value: float):
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"trait value must be in [0,1], got {value}")
        t = trait.encode("ascii").ljust(16, b"\x00")[:16]
        v = int(value * 65535).to_bytes(2, "big")
        self._unit.send_cmd(CMD_TRAIT_SET, t + v)
        log.debug("personality.set %s=%.3f", trait, value)

    def snapshot(self) -> dict[str, float]:
        """Return all traits as a plain dict."""
        raw = self._unit.send_cmd(CMD_TRAIT_SNAPSHOT)
        result = {}
        for i in range(0, len(raw), 18):
            chunk = raw[i:i+18]
            if len(chunk) < 18:
                break
            name = chunk[:16].rstrip(b"\x00").decode("ascii")
            val  = int.from_bytes(chunk[16:18], "big") / 65535.0
            result[name] = round(val, 4)
        return result

    def save(self, path: str = "config/personality_snapshot.json"):
        data = self.snapshot()
        Path(path).write_text(json.dumps(data, indent=2))
        log.info("personality snapshot saved to %s", path)

    def load(self, path: str = "config/personality_snapshot.json"):
        data = json.loads(Path(path).read_text())
        for trait, value in data.items():
            self.set(trait, value)
        log.info("personality snapshot loaded from %s", path)

    def reset(self):
        """
        WARNING: destructive. Resets all traits to factory defaults.
        Back up config/personality_snapshot.json first.
        """
        log.warning("resetting personality to factory defaults")
        self._unit.send_cmd(CMD_TRAIT_RESET, b"\xDE\xAD")
