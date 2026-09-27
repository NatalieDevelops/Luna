"""
ruby.runtime
============
Top-level process manager. Spawns and supervises all subsystem daemons.
Run with:
    python3 -m ruby.runtime --config config.yaml
"""

import argparse
import logging
import signal
import sys
import time
from pathlib import Path

import yaml

from ruby.firmware.neural_unit import NeuralUnit
from ruby.vision.pipeline import VisionPipeline
from ruby.tactile.sensefur import SenseFurArray
from ruby.personality.engine import PersonalityEngine
from ruby.locomotion.controller import LocomotionController
from ruby.audio.purrsynth import PurrSynth
from ruby.power.moodcell import MoodCell
from ruby.memory.store import MemoryStore

log = logging.getLogger("ruby.runtime")


class Runtime:
    """
    Owns all subsystem instances and the main event loop.
    Subsystems communicate via shared MemoryStore and direct method calls.
    """

    def __init__(self, config_path: str):
        with open(config_path) as f:
            self.cfg = yaml.safe_load(f)

        self._setup_logging()
        self._running = False

        log.info("Initializing Ruby runtime v0.9.2")

        # core shared state
        self.memory = MemoryStore(path=self.cfg["personality"]["db"])

        # subsystems
        self.neural   = NeuralUnit(**self.cfg["neural_unit"])
        self.vision   = VisionPipeline(**self.cfg["vision"])
        self.tactile  = SenseFurArray(**self.cfg["tactile"])
        self.affect   = PersonalityEngine(memory=self.memory, **self.cfg["personality"])
        self.loco     = LocomotionController(**self.cfg["locomotion"])
        self.audio    = PurrSynth(**self.cfg["audio"])
        self.power    = MoodCell(**self.cfg["power"])

        self._wire_callbacks()

    def _setup_logging(self):
        cfg = self.cfg.get("logging", {})
        logging.basicConfig(
            level=getattr(logging, cfg.get("level", "INFO")),
            format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
        )

    def _wire_callbacks(self):
        """Connect subsystem event callbacks."""

        @self.vision.on_face
        def on_face(ev):
            self.affect.update(trigger="face_detected", actor_uid=ev.uid,
                               battery_level=self.power.level)
            trust = self.memory.get_trust(ev.uid)
            if trust > 0.5:
                self.audio.play("greeting_warm")
            else:
                self.audio.play("greeting_cautious")

        @self.tactile.on_touch
        def on_touch(ev):
            self.affect.update(trigger=f"touch_{ev.zone}", actor_uid=ev.actor_uid,
                               duration_ms=ev.duration_ms,
                               battery_level=self.power.level)
            self._respond_to_touch(ev)

        @self.power.on_low
        def on_low_battery(level):
            log.warning("Low battery: %.2f -- returning to RestPod", level)
            self.loco.play_gait("return_to_base")

    def _respond_to_touch(self, ev):
        """Map touch events to audio + locomotion responses."""
        affect = self.affect.get_affect()
        zone = ev.zone
        pressure = ev.pressure

        if zone == "head" and pressure > 0.3:
            self.audio.play("purr")
            self.loco.set_pose("head_lean", transition_ms=400)
        elif zone == "chin":
            self.audio.play("purr_loud")
            self.loco.set_pose("chin_up", transition_ms=300)
        elif zone == "back" and pressure > 0.6:
            self.audio.play("chirp")
            self.loco.set_pose("arch_back", transition_ms=500)
        elif zone == "tail":
            self.loco.set_pose("tail_flick", transition_ms=200)
        elif zone == "belly" and affect.trust_avg < 0.5:
            self.audio.play("warning_hiss")
            self.loco.set_pose("defensive_curl", transition_ms=150)

    def start(self):
        log.info("Starting all subsystems")
        self._running = True

        self.neural.connect()
        self.vision.start()
        self.tactile.start()
        self.loco.enable()
        self.audio.connect()
        self.power.start_monitor()

        signal.signal(signal.SIGINT,  self._shutdown)
        signal.signal(signal.SIGTERM, self._shutdown)

        log.info("Ruby is awake")
        self.audio.play("startup_chime")

        while self._running:
            behavior = self.affect.recommend_behavior(self.affect.get_affect())
            self.loco.execute_behavior(behavior)
            time.sleep(0.1)

    def _shutdown(self, *_):
        log.info("Shutting down")
        self._running = False
        self.vision.stop()
        self.tactile.stop()
        self.loco.disable()
        self.audio.play("shutdown_purr")
        self.audio.disconnect()
        self.neural.disconnect()
        self.power.stop_monitor()
        self.memory.close()
        log.info("Goodbye")
        sys.exit(0)


def main():
    parser = argparse.ArgumentParser(description="Ruby companion cat runtime")
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()

    if not Path(args.config).exists():
        print(f"ERROR: config file not found: {args.config}", file=sys.stderr)
        sys.exit(1)

    rt = Runtime(args.config)
    rt.start()


if __name__ == "__main__":
    main()
