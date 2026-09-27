"""
hardware/audio.py

PurrSynth v2.1 audio chip interface.
Communicates over UART. Provides named sound playback and
real-time emotion-to-sound mapping.
"""

import serial
import time
import logging
from typing import Optional

log = logging.getLogger(__name__)

# PurrSynth UART protocol v2.1 command bytes
CMD_PLAY       = 0x10
CMD_STOP       = 0x11
CMD_SET_VOL    = 0x20
CMD_SET_PITCH  = 0x21
CMD_PING       = 0xFE

SOUND_IDS = {
    "purr":          0x01,
    "meow_happy":    0x02,
    "meow_hungry":   0x03,
    "meow_attention":0x04,
    "chirp":         0x05,
    "trill":         0x06,
    "hiss":          0x07,
    "growl":         0x08,
    "purr_deep":     0x09,
    "meow_soft":     0x0A,
}

# affect state -> recommended sound
AFFECT_SOUND_MAP = {
    "playful_approach": "trill",
    "tail_wag":         "purr",
    "vocalise_happy":   "meow_happy",
    "vocalise_content": "purr_deep",
    "alert_scan":       "chirp",
    "cautious_retreat": "growl",
    "sleep":            None,
}


class PurrSynth:
    """
    PurrSynth v2.1 audio interface.

    Example
    -------
    ps = PurrSynth(port="/dev/ttyUSB1")
    ps.play("purr")
    ps.play_for_behavior("playful_approach")
    """

    BAUD = 9600

    def __init__(self, port: str, volume: float = 0.7, voice_profile: str = "ruby_v2"):
        self.port = port
        self._volume = volume
        self._voice_profile = voice_profile
        self._serial: Optional[serial.Serial] = None
        self._connect()

    def _connect(self):
        try:
            self._serial = serial.Serial(self.port, self.BAUD, timeout=1.0)
            time.sleep(0.05)
            self._ping()
            self._set_volume(self._volume)
            log.info("PurrSynth connected on %s", self.port)
        except Exception as e:
            log.warning("PurrSynth connect failed: %s (audio disabled)", e)
            self._serial = None

    def _ping(self):
        if self._serial is None:
            return
        self._serial.write(bytes([CMD_PING]))
        resp = self._serial.read(1)
        if not resp or resp[0] != 0x01:
            raise RuntimeError("PurrSynth ping failed")

    def _write(self, data: bytes):
        if self._serial and self._serial.is_open:
            self._serial.write(data)

    def _set_volume(self, vol: float):
        v = int(max(0.0, min(1.0, vol)) * 255)
        self._write(bytes([CMD_SET_VOL, v]))

    def play(self, sound_name: str, pitch: float = 1.0):
        if sound_name not in SOUND_IDS:
            raise ValueError(f"unknown sound: {sound_name!r}. valid: {list(SOUND_IDS)}")
        sid = SOUND_IDS[sound_name]
        pitch_byte = int(max(0.5, min(2.0, pitch)) / 2.0 * 255)
        self._write(bytes([CMD_SET_PITCH, pitch_byte]))
        self._write(bytes([CMD_PLAY, sid]))
        log.debug("PurrSynth play sound=%s pitch=%.2f", sound_name, pitch)

    def play_for_behavior(self, behavior: str):
        sound = AFFECT_SOUND_MAP.get(behavior)
        if sound:
            self.play(sound)

    def stop(self):
        self._write(bytes([CMD_STOP]))

    def set_volume(self, vol: float):
        self._volume = vol
        self._set_volume(vol)

    def close(self):
        if self._serial and self._serial.is_open:
            self._serial.close()
