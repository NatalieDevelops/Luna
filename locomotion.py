"""
hardware/locomotion.py

FlexBone-X 15-DOF locomotion controller.

Joint map:
  neck_yaw    neck_pitch
       \         /
        [HEAD UNIT]
             |
    shoulder_l  shoulder_r
         |              |
     elbow_l         elbow_r
         |              |
     wrist_l          wrist_r

             |
       [SPINE 4-DOF]
             |
     hip_l       hip_r
       |               |
   knee_l           knee_r

             |
         [TAIL]
       tail_base (2-DOF)
       tail_mid  (1-DOF)
       tail_tip  (TailSense sensor)

Active DOF: 12 body + 3 tail = 15
"""

import time
import logging
import math
from dataclasses import dataclass
from typing import Optional

try:
    import RPi.GPIO as GPIO
except ImportError:
    GPIO = None

log = logging.getLogger(__name__)

# servo channel assignments (PCA9685 PWM driver)
JOINT_CHANNELS = {
    "neck_yaw":     0,
    "neck_pitch":   1,
    "shoulder_l":   2,
    "shoulder_r":   3,
    "elbow_l":      4,
    "elbow_r":      5,
    "wrist_l":      6,
    "wrist_r":      7,
    "spine_0":      8,
    "spine_1":      9,
    "hip_l":        10,
    "hip_r":        11,
    "knee_l":       12,
    "knee_r":       13,
    "tail_base_y":  14,
    "tail_base_p":  15,
}

# servo limits in radians
JOINT_LIMITS = {
    "neck_yaw":    (-1.2,  1.2),
    "neck_pitch":  (-0.8,  0.8),
    "shoulder_l":  (-1.5,  1.5),
    "shoulder_r":  (-1.5,  1.5),
    "elbow_l":     (-1.8,  0.3),
    "elbow_r":     (-1.8,  0.3),
    "wrist_l":     (-0.8,  0.8),
    "wrist_r":     (-0.8,  0.8),
    "spine_0":     (-0.5,  0.5),
    "spine_1":     (-0.5,  0.5),
    "hip_l":       (-1.5,  1.5),
    "hip_r":       (-1.5,  1.5),
    "knee_l":      (-1.8,  0.2),
    "knee_r":      (-1.8,  0.2),
    "tail_base_y": (-1.5,  1.5),
    "tail_base_p": (-1.0,  1.0),
}

# named poses: joint -> radians
POSES = {
    "stand": {
        "shoulder_l": -0.2, "shoulder_r": -0.2,
        "elbow_l":    -1.2, "elbow_r":    -1.2,
        "hip_l":      -0.2, "hip_r":      -0.2,
        "knee_l":     -1.2, "knee_r":     -1.2,
        "neck_pitch":  0.0, "neck_yaw":    0.0,
    },
    "sit": {
        "shoulder_l": -0.4, "shoulder_r": -0.4,
        "elbow_l":    -1.0, "elbow_r":    -1.0,
        "hip_l":       0.8, "hip_r":       0.8,
        "knee_l":     -1.6, "knee_r":     -1.6,
        "neck_pitch":  0.1,
    },
    "curl_up": {
        "shoulder_l": -0.6, "shoulder_r": -0.6,
        "elbow_l":    -1.5, "elbow_r":    -1.5,
        "hip_l":       1.0, "hip_r":       1.0,
        "knee_l":     -1.7, "knee_r":     -1.7,
        "spine_0":     0.4, "spine_1":     0.3,
        "neck_pitch":  0.3, "tail_base_p":  0.8,
    },
}


@dataclass
class JointState:
    name: str
    channel: int
    current_rad: float = 0.0
    target_rad: float  = 0.0
    limits: tuple = (-math.pi, math.pi)

    def clamp(self, val: float) -> float:
        return max(self.limits[0], min(self.limits[1], val))

    def set(self, rad: float):
        self.target_rad = self.clamp(rad)


class LocomotionController:
    """
    FlexBone-X servo controller.

    Example
    -------
    loco = LocomotionController()
    loco.play_gait("trot", speed=0.4)
    loco.set_pose("sit", transition_ms=800)
    loco.joints["neck_pitch"].set(0.3)
    """

    SERVO_HZ = 50
    MIN_PULSE_US = 500
    MAX_PULSE_US = 2500

    def __init__(self):
        self.joints: dict[str, JointState] = {
            name: JointState(
                name=name,
                channel=ch,
                limits=JOINT_LIMITS.get(name, (-math.pi, math.pi))
            )
            for name, ch in JOINT_CHANNELS.items()
        }
        self._pwm = None
        self._init_pwm()

    def _init_pwm(self):
        try:
            import smbus2
            self._bus = smbus2.SMBus(1)
            log.info("PCA9685 PWM driver initialized on I2C bus 1")
        except Exception as e:
            log.warning("PWM init failed (hardware not present?): %s", e)

    def _rad_to_pulse_us(self, rad: float, limits: tuple) -> int:
        lo, hi = limits
        t = (rad - lo) / (hi - lo)
        t = max(0.0, min(1.0, t))
        return int(self.MIN_PULSE_US + t * (self.MAX_PULSE_US - self.MIN_PULSE_US))

    def _write_servo(self, channel: int, pulse_us: int):
        """Write pulse width to PCA9685 channel. Stubbed if no hardware."""
        if self._pwm is None:
            return
        period_us = 1_000_000.0 / self.SERVO_HZ
        on_ticks  = 0
        off_ticks = int(pulse_us / period_us * 4096)
        # PCA9685 register layout: base + channel*4
        reg = 0x06 + channel * 4
        data = [
            on_ticks & 0xFF, (on_ticks >> 8) & 0x0F,
            off_ticks & 0xFF, (off_ticks >> 8) & 0x0F
        ]
        try:
            self._bus.write_i2c_block_data(0x40, reg, data)
        except Exception as e:
            log.debug("servo write error ch=%d: %s", channel, e)

    def set_pose(self, pose_name: str, transition_ms: int = 500):
        if pose_name not in POSES:
            raise ValueError(f"unknown pose: {pose_name!r}. valid: {list(POSES)}")
        target = POSES[pose_name]
        steps  = max(1, transition_ms // 20)
        dt     = transition_ms / 1000.0 / steps

        start = {name: j.current_rad for name, j in self.joints.items()}
        for step in range(steps + 1):
            t = step / steps
            for name, target_rad in target.items():
                j = self.joints.get(name)
                if j is None:
                    continue
                interp = start[name] + (target_rad - start[name]) * t
                clamped = j.clamp(interp)
                pulse = self._rad_to_pulse_us(clamped, j.limits)
                self._write_servo(j.channel, pulse)
                j.current_rad = clamped
            time.sleep(dt)
        log.info("pose=%s complete", pose_name)

    def play_gait(self, gait_name: str, speed: float = 0.5, cycles: int = -1):
        """
        Play a named gait from config/gaits/<gait_name>.yaml.
        speed: 0.0..1.0 (scales timing)
        cycles: -1 = continuous until stop() called
        """
        import yaml, pathlib
        path = pathlib.Path(f"config/gaits/{gait_name}.yaml")
        if not path.exists():
            raise FileNotFoundError(f"gait file not found: {path}")
        gait = yaml.safe_load(path.read_text())
        log.info("playing gait=%s speed=%.2f", gait_name, speed)
        # gait execution is delegated to the gait interpreter
        # (see config/gaits/README.md for format spec)

    def center_all(self, transition_ms: int = 1000):
        """Move all joints to center position."""
        for j in self.joints.values():
            j.target_rad = 0.0
        steps = max(1, transition_ms // 20)
        for step in range(steps + 1):
            t = step / steps
            for j in self.joints.values():
                interp = j.current_rad * (1.0 - t)
                j.current_rad = interp
                pulse = self._rad_to_pulse_us(interp, j.limits)
                self._write_servo(j.channel, pulse)
            time.sleep(0.02)
