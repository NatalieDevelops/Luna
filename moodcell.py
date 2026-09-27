"""
power.moodcell
==============
MoodCell 4400mAh adaptive battery interface.
Reads state-of-charge from analog GPIO + ADC.
Fires callbacks at low-battery threshold.
RestPod charging managed via GPIO trigger pin.

GPIO pinout (BCM numbering):
    GPIO17  -- MoodCell analog SOC (via MCP3008 ADC CH0)
    GPIO18  -- RestPod charge enable (HIGH = charging)
    GPIO27  -- RestPod docked sense (HIGH = on base)
"""

import threading
import time
from typing import Callable, List, Optional


class MoodCell:

    def __init__(self, restpod_charge_threshold: float = 0.25,
                 restpod_full_threshold: float = 0.95,
                 mood_signal_enabled: bool = True,
                 low_power_mode_threshold: float = 0.10, **_):
        self._charge_thresh = restpod_charge_threshold
        self._full_thresh   = restpod_full_threshold
        self._mood_enabled  = mood_signal_enabled
        self._low_thresh    = low_power_mode_threshold

        self._level: float = 1.0
        self._charging: bool = False
        self._docked: bool = False
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._low_callbacks: List[Callable] = []
        self._gpio = None
        self._adc  = None

    def on_low(self, fn: Callable) -> Callable:
        self._low_callbacks.append(fn)
        return fn

    @property
    def level(self) -> float:
        return self._level

    @property
    def charging(self) -> bool:
        return self._charging

    def start_monitor(self):
        self._init_gpio()
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()

    def stop_monitor(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)

    def _init_gpio(self):
        try:
            import RPi.GPIO as GPIO
            import spidev
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(18, GPIO.OUT, initial=GPIO.LOW)
            GPIO.setup(27, GPIO.IN,  pull_up_down=GPIO.PUD_DOWN)
            self._gpio = GPIO
            self._spi  = spidev.SpiDev()
            self._spi.open(0, 0)
            self._spi.max_speed_hz = 1350000
        except ImportError:
            self._gpio = None

    def _read_soc(self) -> float:
        if self._gpio is None:
            # simulation: fake discharge curve
            return self._level
        # MCP3008 read CH0
        r = self._spi.xfer2([1, 0x80, 0])
        raw = ((r[1] & 3) << 8) | r[2]
        return raw / 1023.0

    def _monitor_loop(self):
        while self._running:
            self._level = self._read_soc()

            if self._gpio:
                self._docked = bool(self._gpio.input(27))

            # auto-manage charging
            if self._level < self._charge_thresh and self._docked:
                self._set_charging(True)
            elif self._level >= self._full_thresh:
                self._set_charging(False)

            if self._level < self._low_thresh:
                for cb in self._low_callbacks:
                    cb(self._level)

            time.sleep(10.0)

    def _set_charging(self, state: bool):
        if self._charging == state:
            return
        self._charging = state
        if self._gpio:
            self._gpio.output(18, self._gpio.HIGH if state else self._gpio.LOW)
