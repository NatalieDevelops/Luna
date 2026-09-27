"""Unit tests for personality.engine.PersonalityEngine"""

import tempfile

import pytest

from ruby.memory.store import MemoryStore
from ruby.personality.engine import PersonalityEngine, AffectState


@pytest.fixture
def engine():
    with tempfile.NamedTemporaryFile(suffix=".db") as f:
        mem = MemoryStore(path=f.name)
        eng = PersonalityEngine(memory=mem, trait_drift_rate=0.001,
                                mood_decay_rate=0.0005, trust_decay_rate=0.0001)
        yield eng
        mem.close()


def test_initial_affect_is_neutral(engine):
    affect = engine.get_affect()
    assert affect.mood == pytest.approx(0.5)


def test_positive_touch_raises_mood(engine):
    engine.update("touch_chin", actor_uid="user_0", battery_level=0.8)
    affect = engine.get_affect()
    assert affect.mood > 0.5


def test_belly_touch_lowers_mood(engine):
    engine.update("touch_belly", actor_uid="user_0", battery_level=0.8)
    affect = engine.get_affect()
    assert affect.mood < 0.5


def test_battery_level_sets_energy(engine):
    engine.update("face_detected", actor_uid="user_0", battery_level=0.2)
    assert engine.get_affect().energy == pytest.approx(0.2)


def test_behavior_recommendation_returns_string(engine):
    affect = AffectState(mood=0.8, energy=0.8, trust_map={"u": 0.9})
    b = engine.recommend_behavior(affect)
    assert isinstance(b, str)
    assert len(b) > 0


def test_curl_up_recommended_at_low_energy(engine):
    affect = AffectState(mood=0.6, energy=0.2, trust_map={"u": 0.6})
    b = engine.recommend_behavior(affect)
    assert b == "curl_up"


def test_snapshot_returns_all_traits(engine):
    snap = engine.snapshot()
    for trait in ("bold", "playful", "cautious", "affectionate", "curious", "independent"):
        assert trait in snap
        assert 0.0 <= snap[trait] <= 1.0
