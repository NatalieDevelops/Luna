"""
firmware/instinct.py

Hardcoded behavioral drives that feed into the instinct model
running on the neural unit.
Drive weights are written to the unit over serial and persist
in onboard flash until explicitly changed.
"""

from __future__ import annotations
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .neural_unit import NeuralUnit

log = logging.getLogger(__name__)

# CMD IDs (firmware protocol v3)
CMD_SET_DRIVE = 0x20
CMD_GET_DRIVE = 0x21
CMD_LIST_DRIVES = 0x22

DEFAULT_DRIVES = {
    "curiosity":    0.7,
    "social":       0.85,
    "rest":         0.4,
    "hunger":       0.5,
    "play":         0.75,
    "self_preserve": 0.9,
}


class InstinctModel:
    def __init__(self, unit: NeuralUnit):
        self._unit = unit
        self._cache: dict[str, float] = {}

    def set_drive(self, name: str, weight: float):
        """
        Set a drive weight on the neural unit (0.0 .. 1.0).
        Drive names are null-padded to 16 bytes in the wire format.
        """
        if not 0.0 <= weight <= 1.0:
            raise ValueError(f"drive weight must be in [0,1], got {weight}")
        name_bytes = name.encode("ascii").ljust(16, b"\x00")[:16]
        w_bytes = int(weight * 65535).to_bytes(2, "big")
        self._unit.send_cmd(CMD_SET_DRIVE, name_bytes + w_bytes)
        self._cache[name] = weight
        log.debug("set_drive %s=%.3f", name, weight)

    def get_drive(self, name: str) -> float:
        name_bytes = name.encode("ascii").ljust(16, b"\x00")[:16]
        raw = self._unit.send_cmd(CMD_GET_DRIVE, name_bytes)
        val = int.from_bytes(raw[:2], "big") / 65535.0
        self._cache[name] = val
        return val

    def list_drives(self) -> dict[str, float]:
        raw = self._unit.send_cmd(CMD_LIST_DRIVES)
        result = {}
        for i in range(0, len(raw), 18):
            chunk = raw[i:i+18]
            if len(chunk) < 18:
                break
            name = chunk[:16].rstrip(b"\x00").decode("ascii")
            val  = int.from_bytes(chunk[16:18], "big") / 65535.0
            result[name] = val
        self._cache.update(result)
        return result

    def load_defaults(self):
        for name, weight in DEFAULT_DRIVES.items():
            self.set_drive(name, weight)
