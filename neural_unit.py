"""
firmware.neural_unit
====================
Serial interface to the Claude Neural Unit v3 running OpenClaw firmware.
Exposes instinct modeling, episodic memory formation, and personality engine
over a framed UART protocol.

Protocol frames:
    [0xAA] [LEN:2] [CMD:1] [PAYLOAD:LEN] [CRC8:1]

Commands:
    0x01  SET_DRIVE       set instinct drive weight
    0x02  GET_DRIVES      query all drive weights
    0x10  ENCODE_EVENT    write episodic memory event
    0x11  GET_TRUST       query trust score for uid
    0x20  GET_PERSONALITY snapshot current trait vector
    0x21  RESET_PERSONALITY factory reset traits
    0x30  PING
"""

import struct
import threading
import time
from dataclasses import dataclass, field
from typing import Dict

import serial


FRAME_HEADER = 0xAA
BAUD_DEFAULT = 115200


def _crc8(data: bytes) -> int:
    crc = 0
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc << 1) ^ 0x07 if crc & 0x80 else crc << 1
        crc &= 0xFF
    return crc


@dataclass
class PersonalitySnapshot:
    bold:          float = 0.5
    playful:       float = 0.5
    cautious:      float = 0.5
    affectionate:  float = 0.5
    curious:       float = 0.5
    independent:   float = 0.5

    def __repr__(self):
        return (
            f"PersonalitySnapshot("
            f"bold={self.bold:.2f}, playful={self.playful:.2f}, "
            f"cautious={self.cautious:.2f}, affectionate={self.affectionate:.2f}, "
            f"curious={self.curious:.2f}, independent={self.independent:.2f})"
        )


class InstinctModel:
    """Manage behavioral drive weights on the neural unit."""

    DRIVES = ("curiosity", "social", "rest", "play", "hunt", "groom")

    def __init__(self, uart):
        self._uart = uart
        self._drives: Dict[str, float] = {d: 0.5 for d in self.DRIVES}

    def set_drive(self, drive: str, weight: float):
        if drive not in self.DRIVES:
            raise ValueError(f"Unknown drive: {drive!r}. Valid: {self.DRIVES}")
        weight = max(0.0, min(1.0, weight))
        payload = drive.encode().ljust(16, b"\x00") + struct.pack("f", weight)
        self._uart._send(0x01, payload)
        self._drives[drive] = weight

    def get_drives(self) -> Dict[str, float]:
        self._uart._send(0x02, b"")
        resp = self._uart._recv()
        # parse 6x (16-char name + float) pairs
        for i in range(6):
            name = resp[i*20:i*20+16].rstrip(b"\x00").decode()
            val  = struct.unpack_from("f", resp, i*20+16)[0]
            self._drives[name] = val
        return dict(self._drives)


class MemoryInterface:
    """Read/write episodic memory on the neural unit's flash store."""

    def __init__(self, uart):
        self._uart = uart

    def encode(self, event: str, uid: str, valence: float):
        """
        Write a memory event. valence in [-1.0, +1.0].
        Positive = good interaction, negative = aversive.
        """
        payload = (
            event.encode().ljust(32, b"\x00") +
            uid.encode().ljust(16, b"\x00") +
            struct.pack("f", valence)
        )
        self._uart._send(0x10, payload)

    def get_trust(self, uid: str) -> float:
        """
        Return trust score for a user ID in [0.0, 1.0].
        Score is computed as weighted sum of past valence events.
        Returns 0.0 for unknown uid.
        """
        payload = uid.encode().ljust(16, b"\x00")
        self._uart._send(0x11, payload)
        resp = self._uart._recv()
        return struct.unpack("f", resp[:4])[0]


class PersonalityInterface:
    """Read and reset personality trait vector."""

    def __init__(self, uart):
        self._uart = uart

    def snapshot(self) -> PersonalitySnapshot:
        self._uart._send(0x20, b"")
        resp = self._uart._recv()
        vals = struct.unpack("6f", resp[:24])
        return PersonalitySnapshot(*vals)

    def reset(self):
        """
        DESTRUCTIVE: resets all traits to 0.5 and clears memory.
        Back up config/personality_snapshot.json first.
        """
        self._uart._send(0x21, b"CONFIRM_RESET")


class NeuralUnit:
    """
    Top-level interface to the Claude Neural Unit v3.

    Usage:
        unit = NeuralUnit(port="/dev/ttyUSB0")
        unit.connect()
        unit.instinct.set_drive("social", 0.8)
        unit.memory.encode("chin_scratch", uid="user_0", valence=+0.7)
        snap = unit.personality.snapshot()
    """

    def __init__(self, port: str, baud: int = BAUD_DEFAULT,
                 personality_persistence: bool = True,
                 snapshot_interval_s: int = 300, **_):
        self._port = port
        self._baud = baud
        self._persistence = personality_persistence
        self._snap_interval = snapshot_interval_s
        self._ser: serial.Serial | None = None
        self._lock = threading.Lock()
        self._snap_thread: threading.Thread | None = None

        self.instinct   = InstinctModel(self)
        self.memory      = MemoryInterface(self)
        self.personality = PersonalityInterface(self)

    def connect(self):
        self._ser = serial.Serial(self._port, self._baud, timeout=1.0)
        self._send(0x30, b"")  # PING
        resp = self._recv()
        if resp[:4] != b"PONG":
            raise RuntimeError("Neural unit did not respond to PING")
        if self._persistence:
            self._snap_thread = threading.Thread(
                target=self._snapshot_loop, daemon=True)
            self._snap_thread.start()

    def disconnect(self):
        if self._ser:
            self._ser.close()

    def _send(self, cmd: int, payload: bytes):
        frame = bytes([FRAME_HEADER]) + struct.pack(">H", len(payload)) + bytes([cmd]) + payload
        frame += bytes([_crc8(frame[1:])])
        with self._lock:
            self._ser.write(frame)

    def _recv(self) -> bytes:
        with self._lock:
            hdr = self._ser.read(4)
            if len(hdr) < 4 or hdr[0] != FRAME_HEADER:
                raise IOError("Bad frame header from neural unit")
            length = struct.unpack(">H", hdr[1:3])[0]
            payload = self._ser.read(length)
            crc = self._ser.read(1)[0]
            if crc != _crc8(hdr[1:] + payload):
                raise IOError("CRC mismatch in neural unit response")
            return payload

    def _snapshot_loop(self):
        import json, pathlib
        path = pathlib.Path("config/personality_snapshot.json")
        while True:
            time.sleep(self._snap_interval)
            snap = self.personality.snapshot()
            path.write_text(json.dumps(snap.__dict__, indent=2))
