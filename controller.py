"""
locomotion.controller
=====================
LocomotionController: FlexBone-X 15-DOF servo controller.

Joint Map:
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
          spine_0..spine_3
               |
       hip_l       hip_r
         |               |
     knee_l           knee_r
               |
           [TAIL]
         tail_base_yaw
         tail_base_pitch
         tail_mid

Servo driver: PCA9685 over I2C (addr 0x40), 50Hz PWM.
Angle -> pulse width: pw = 500 + (angle_deg / 180.0) * 2000  [microseconds]
"""

import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

import yaml


JOINT_CHANNEL: Dict[str, int] = {
    "neck_yaw":         0,
    "neck_pitch":       1,
    "shoulder_l":       2,
    "shoulder_r":       3,
    "elbow_l":          4,
    "elbow_r":          5,
    "wrist_l":          6,
    "wrist_r":          7,
    "spine_0":          8,
    "spine_1":          9,
    "spine_2":          10,
    "spine_3":          11,
    "hip_l":            12,
    "hip_r":            13,
    "knee_l":           14,
    "knee_r":           15,
    "tail_base_yaw":    16,
    "tail_base_pitch":  17,
    "tail_mid":         18,
}

HOME_ANGLES: Dict[str, float] = {
    "neck_yaw": 0, "neck_pitch": 0,
    "shoulder_l": 0, "shoulder_r": 0,
    "elbow_l": 90, "elbow_r": 90,
    "wrist_l": 0, "wrist_r": 0,
    "spine_0": 0, "spine_1": 0, "spine_2": 0, "spine_3": 0,
    "hip_l": 0, "hip_r": 0,
    "knee_l": 90, "knee_r": 90,
    "tail_base_yaw": 0, "tail_base_pitch": 10, "tail_mid": 0,
}


def _angle_to_pw(deg: float) -> int:
    """Convert angle in degrees [-90, 90] to PCA9685 pulse width counts."""
    deg = max(-90.0, min(90.0, deg))
    pw_us = 500 + ((deg + 90.0) / 180.0) * 2000
    return int(pw_us / 20000.0 * 4096)


class Joint:
    def __init__(self, name: str, channel: int, driver):
        self.name = name
        self.channel = channel
        self._driver = driver
        self._angle = 0.0

    @property
    def angle(self) -> float:
        return self._angle

    def set(self, angle_rad: float, speed: float = 1.0):
        """Set joint angle in radians. speed in [0,1] (unused in sim)."""
        import math
        deg = math.degrees(angle_rad)
        self._angle = deg
        if self._driver:
            self._driver.set_pwm(self.channel, 0, _angle_to_pw(deg))

    def set_deg(self, deg: float):
        import math
        self.set(math.radians(deg))


class LocomotionController:
    """
    Manages all FlexBone-X servos via PCA9685.

    Usage:
        loco = LocomotionController(servo_hz=50, gait_library="config/gaits/")
        loco.enable()
        loco.set_pose("sit", transition_ms=600)
        loco.play_gait("trot", speed=0.4)
        loco.joints["neck_pitch"].set(0.3)
    """

    def __init__(self, servo_hz: int = 50, max_torque_nm: float = 2.5,
                 gait_library: str = "config/gaits/",
                 home_pose_ms: int = 200, **_):
        self._hz          = servo_hz
        self._max_torque  = max_torque_nm
        self._gait_dir    = Path(gait_library)
        self._home_ms     = home_pose_ms
        self._driver      = None
        self._enabled     = False
        self._gait_thread: Optional[threading.Thread] = None
        self._gait_stop   = threading.Event()

        self._poses  = self._load_poses()
        self.joints  = {
            name: Joint(name, ch, self._driver)
            for name, ch in JOINT_CHANNEL.items()
        }

    def _load_poses(self) -> dict:
        """Load named poses from YAML files in gait_library."""
        poses = {}
        if self._gait_dir.exists():
            for f in self._gait_dir.glob("*.yaml"):
                try:
                    data = yaml.safe_load(f.read_text())
                    poses.update(data.get("poses", {}))
                except Exception:
                    pass
        # hardcoded fallback poses
        poses.setdefault("sit",           {"spine_0": 30, "hip_l": -45, "hip_r": -45, "knee_l": 80, "knee_r": 80})
        poses.setdefault("head_lean",     {"neck_pitch": 20, "neck_yaw": 0})
        poses.setdefault("chin_up",       {"neck_pitch": 30})
        poses.setdefault("arch_back",     {"spine_1": 20, "spine_2": 20})
        poses.setdefault("tail_flick",    {"tail_base_yaw": 45, "tail_mid": -20})
        poses.setdefault("defensive_curl",{"spine_0": 40, "spine_1": 40, "neck_pitch": -10})
        poses.setdefault("idle_sit",      {"neck_pitch": 5, "tail_base_pitch": 15})
        return poses

    def enable(self):
        try:
            from adafruit_pca9685 import PCA9685
            import board, busio
            i2c = busio.I2C(board.SCL, board.SDA)
            self._driver = PCA9685(i2c)
            self._driver.frequency = self._hz
            # update joint driver references
            for j in self.joints.values():
                j._driver = self._driver
        except ImportError:
            pass  # simulation mode: no hardware
        self._enabled = True
        self.set_pose("idle_sit", transition_ms=self._home_ms)

    def disable(self):
        self._enabled = False
        self._gait_stop.set()
        if self._driver:
            try:
                self._driver.deinit()
            except Exception:
                pass

    def set_pose(self, pose_name: str, transition_ms: int = 500):
        """Transition all joints to a named pose."""
        if pose_name not in self._poses:
            return
        targets = self._poses[pose_name]
        steps = max(1, transition_ms // 20)
        start = {name: j.angle for name, j in self.joints.items()}

        for step in range(steps + 1):
            t = step / steps
            for joint_name, target_deg in targets.items():
                if joint_name in self.joints:
                    current = start.get(joint_name, 0.0)
                    interp = current + (target_deg - current) * t
                    self.joints[joint_name].set_deg(interp)
            time.sleep(transition_ms / steps / 1000.0)

    def play_gait(self, gait_name: str, speed: float = 0.5):
        """Play a named cyclic gait. Runs in background thread."""
        gait_file = self._gait_dir / f"{gait_name}.yaml"
        if not gait_file.exists():
            return
        data = yaml.safe_load(gait_file.read_text())
        frames: List[dict] = data.get("frames", [])
        period_s: float = data.get("period_s", 1.0) / max(0.1, speed)

        self._gait_stop.clear()
        if self._gait_thread and self._gait_thread.is_alive():
            self._gait_stop.set()
            self._gait_thread.join(timeout=2.0)
        self._gait_stop.clear()

        def _run():
            while not self._gait_stop.is_set():
                for frame in frames:
                    if self._gait_stop.is_set():
                        break
                    for jname, angle in frame.items():
                        if jname in self.joints:
                            self.joints[jname].set_deg(angle)
                    time.sleep(period_s / max(1, len(frames)))

        self._gait_thread = threading.Thread(target=_run, daemon=True)
        self._gait_thread.start()

    def execute_behavior(self, behavior: str):
        """Map a behavior name from PersonalityEngine to locomotion actions."""
        BEHAVIOR_MAP = {
            "playful_approach":  ("trot",      0.6),
            "slow_explore":      ("walk",       0.3),
            "alert_scan":        ("scan_turn",  0.4),
            "curl_up":           (None,         0),
            "grooming_sit":      (None,         0),
            "defensive_curl":    (None,         0),
            "idle_sit":          (None,         0),
        }
        gait, speed = BEHAVIOR_MAP.get(behavior, (None, 0))
        if gait:
            self.play_gait(gait, speed)
        else:
            self._gait_stop.set()
            self.set_pose(behavior if behavior in self._poses else "idle_sit",
                          transition_ms=800)
