"""
personality/engine.py

Software-side personality + affect engine.
Integrates with the neural unit firmware personality layer
and the local MemoryStore to produce affect states and
behavior recommendations.
"""

import logging
import math
import time
from dataclasses import dataclass, field
from typing import Optional

from .store import MemoryStore

log = logging.getLogger(__name__)

BEHAVIORS = [
    "playful_approach",
    "slow_walk",
    "curl_up",
    "alert_scan",
    "head_rub",
    "tail_wag",
    "roll_over",
    "vocalise_happy",
    "vocalise_content",
    "sleep",
    "cautious_retreat",
    "sit_and_watch",
]


@dataclass
class AffectState:
    mood: float = 0.5           # 0.0 (distressed) .. 1.0 (elated)
    energy: float = 0.5         # 0.0 (exhausted) .. 1.0 (fully charged)
    trust: dict = field(default_factory=dict)   # uid -> 0.0..1.0
    timestamp: float = field(default_factory=time.time)


class PersonalityEngine:
    """
    Software-side personality + affect engine.

    Example
    -------
    mem = MemoryStore(path="data/ruby.db")
    pe  = PersonalityEngine(memory=mem)

    pe.update(trigger="chin_scratch", actor_uid="user_0",
              duration_ms=4200, battery_level=0.78)

    affect = pe.get_affect()
    # AffectState(mood=0.72, energy=0.78, trust={'user_0': 0.84})

    behavior = pe.recommend_behavior(affect)
    # 'playful_approach'
    """

    MOOD_DECAY_RATE   = 0.0005   # per second, toward neutral (0.5)
    TRAIT_DRIFT_RATE  = 0.001    # per positive interaction event

    POSITIVE_TRIGGERS = {
        "chin_scratch", "head_pet", "back_stroke", "play_initiated", "fed",
    }
    NEGATIVE_TRIGGERS = {
        "tail_grab", "loud_noise", "picked_up", "ignored",
    }

    def __init__(self, memory: Optional[MemoryStore] = None):
        self._memory = memory or MemoryStore()
        self._mood   = 0.5
        self._last_update = time.time()

    def _decay_mood(self):
        now = time.time()
        dt = now - self._last_update
        delta = (0.5 - self._mood) * self.MOOD_DECAY_RATE * dt
        self._mood = max(0.0, min(1.0, self._mood + delta))
        self._last_update = now

    def update(
        self,
        trigger: str,
        actor_uid: str,
        duration_ms: int = 0,
        battery_level: float = 1.0,
    ):
        self._decay_mood()

        if trigger in self.POSITIVE_TRIGGERS:
            strength = min(1.0, duration_ms / 5000.0) * 0.3
            self._mood = min(1.0, self._mood + strength)
            self._memory.record_interaction(actor_uid, valence=+strength)
            log.debug("positive trigger=%s mood -> %.3f", trigger, self._mood)

        elif trigger in self.NEGATIVE_TRIGGERS:
            strength = 0.15
            self._mood = max(0.0, self._mood - strength)
            self._memory.record_interaction(actor_uid, valence=-strength)
            log.debug("negative trigger=%s mood -> %.3f", trigger, self._mood)

        self._last_update = time.time()

    def get_affect(self, battery_level: float = 1.0) -> AffectState:
        self._decay_mood()
        trust = self._memory.get_all_trust()
        return AffectState(
            mood=round(self._mood, 4),
            energy=round(battery_level, 4),
            trust=trust,
        )

    def recommend_behavior(self, affect: AffectState) -> str:
        mood   = affect.mood
        energy = affect.energy

        if energy < 0.2:
            return "sleep"
        if mood > 0.75 and energy > 0.6:
            return "playful_approach"
        if mood > 0.65:
            return "tail_wag" if energy > 0.4 else "vocalise_content"
        if mood > 0.5:
            return "slow_walk" if energy > 0.5 else "sit_and_watch"
        if mood < 0.3:
            return "cautious_retreat"
        return "alert_scan"
