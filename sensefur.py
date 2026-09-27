"""
tactile.sensefur
================
SenseFur v2 -- 128-point capacitive pressure + temperature fiber array.
Hardware: ATtiny84 multiplexer over I2C at 0x48.
Sample rate: 100 Hz (configurable).

Zone map (top view):
                           .------.
                          /  HEAD  \
              [zone: head] --+--+-- [zone: ears]
                            |     |
               .---[back]---.     .---[back]---.
              |                                 |
              '--.                           .--'
                  \                         /
               [zone: flank]         [zone: flank]
                  |                         |
               .--'-------------------------'--.
              |             BELLY              |
               '--------------------------------'
                  |    |               |    |
              [paw_fl][paw_fr]     [paw_rl][paw_rr]

Fiber index -> zone mapping defined in ZONE_MAP below.
"""

import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np


ZONE_MAP: Dict[str, Tuple[int, int]] = {
    "head":    (0,   31),
    "back":    (32,  63),
    "belly":   (64,  95),
    "paw_fl":  (96,  103),
    "paw_fr":  (104, 111),
    "paw_rl":  (112, 119),
    "paw_rr":  (120, 127),
}


def _index_to_zone(idx: int) -> str:
    for zone, (lo, hi) in ZONE_MAP.items():
        if lo <= idx <= hi:
            return zone
    return "unknown"


@dataclass
class TactileEvent:
    zone:        str
    pressure:    float        # 0.0 .. 1.0
    temp_c:      float
    duration_ms: int
    fiber_idx:   int
    actor_uid:   str = "unknown"
    frame_ts:    float = field(default_factory=time.time)


class SenseFurArray:
    """
    Reads 128 fiber points at up to 100 Hz via I2C.
    Fires on_touch callbacks when sustained pressure exceeds threshold.

    Usage:
        sf = SenseFurArray(i2c_bus=1, i2c_address=0x48, sample_rate_hz=100,
                           calibration_file="config/sensefur_cal.bin")

        @sf.on_touch
        def handler(ev: TactileEvent):
            print(ev.zone, ev.pressure)

        sf.start()  # non-blocking
    """

    PRESSURE_THRESHOLD = 0.08   # min pressure to register as touch
    TOUCH_MIN_MS       = 50     # ignore taps shorter than 50ms
    N_FIBERS           = 128
    BYTES_PER_FRAME    = N_FIBERS * 2  # 1 byte pressure + 1 byte temp per fiber

    def __init__(self, i2c_bus: int = 1, i2c_address: int = 0x48,
                 sample_rate_hz: int = 100,
                 calibration_file: str = "config/sensefur_cal.bin",
                 zones: Optional[Dict] = None, **_):
        self._bus_id = i2c_bus
        self._addr   = i2c_address
        self._hz     = sample_rate_hz
        self._period = 1.0 / sample_rate_hz
        self._cal_file = calibration_file

        self._callbacks: List[Callable] = []
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._bus = None

        # per-fiber baseline (loaded from calibration file)
        self._baseline = np.zeros(self.N_FIBERS, dtype=np.float32)

        # touch tracking: (start_time, last_pressure) per active fiber
        self._active: Dict[int, Tuple[float, float]] = {}

    # ------------------------------------------------------------------

    def on_touch(self, fn: Callable) -> Callable:
        self._callbacks.append(fn)
        return fn

    # ------------------------------------------------------------------

    def start(self):
        self._load_calibration()
        self._open_i2c()
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)

    # ------------------------------------------------------------------

    def _load_calibration(self):
        try:
            self._baseline = np.fromfile(self._cal_file, dtype=np.float32)
            assert len(self._baseline) == self.N_FIBERS
        except (FileNotFoundError, AssertionError):
            self._baseline = np.zeros(self.N_FIBERS, dtype=np.float32)

    def _open_i2c(self):
        try:
            import smbus2
            self._bus = smbus2.SMBus(self._bus_id)
        except ImportError:
            self._bus = None  # simulation mode

    def _read_frame(self) -> Tuple[np.ndarray, np.ndarray]:
        """
        Read one full frame from the ATtiny84 mux.
        Returns (pressure[128], temp_c[128]).
        """
        if self._bus is None:
            # simulation: random noise for testing without hardware
            raw = np.random.randint(0, 30, self.N_FIBERS, dtype=np.uint8)
            temps = (np.random.randn(self.N_FIBERS) * 0.5 + 32.0).astype(np.float32)
            return raw.astype(np.float32) / 255.0, temps

        raw = self._bus.read_i2c_block_data(
            self._addr, 0x00, self.BYTES_PER_FRAME)
        pressure = np.array(raw[0::2], dtype=np.float32) / 255.0
        temp_raw = np.array(raw[1::2], dtype=np.float32)
        temp_c   = (temp_raw / 255.0) * 60.0 + 10.0  # 10-70C range
        return pressure, temp_c

    def _loop(self):
        t_next = time.monotonic()
        while self._running:
            t_now = time.monotonic()
            if t_now < t_next:
                time.sleep(t_next - t_now)
            t_next += self._period

            pressure, temp_c = self._read_frame()
            adjusted = pressure - self._baseline
            now_ms = time.time() * 1000.0

            for idx in range(self.N_FIBERS):
                p = float(adjusted[idx])
                if p > self.PRESSURE_THRESHOLD:
                    if idx not in self._active:
                        self._active[idx] = (now_ms, p)
                    # update last pressure
                    start_ms, _ = self._active[idx]
                    self._active[idx] = (start_ms, p)
                else:
                    if idx in self._active:
                        start_ms, last_p = self._active.pop(idx)
                        duration = int(now_ms - start_ms)
                        if duration >= self.TOUCH_MIN_MS:
                            ev = TactileEvent(
                                zone=_index_to_zone(idx),
                                pressure=last_p,
                                temp_c=float(temp_c[idx]),
                                duration_ms=duration,
                                fiber_idx=idx,
                            )
                            for cb in self._callbacks:
                                cb(ev)


class SenseFurCalibrator:
    """
    Captures baseline readings for SenseFur calibration.
    Run via: python3 scripts/calibrate_sensefur.py
    """

    def __init__(self, array: SenseFurArray, samples: int = 500):
        self._array = array
        self._samples = samples

    def run(self, output_path: str):
        print(f"Collecting {self._samples} baseline samples...")
        print("Do NOT touch Ruby during calibration.")
        readings = []
        for i in range(self._samples):
            p, _ = self._array._read_frame()
            readings.append(p)
            if i % 50 == 0:
                print(f"  {i}/{self._samples}")
            time.sleep(0.01)

        baseline = np.mean(readings, axis=0).astype(np.float32)
        baseline.tofile(output_path)
        print(f"Calibration saved to {output_path}")
        print(f"  mean={baseline.mean():.4f}  max={baseline.max():.4f}")
