"""Unit tests for memory.store.MemoryStore"""

import tempfile
import time

import pytest

from ruby.memory.store import MemoryStore


@pytest.fixture
def store():
    with tempfile.NamedTemporaryFile(suffix=".db") as f:
        s = MemoryStore(path=f.name)
        yield s
        s.close()


def test_unknown_uid_returns_neutral(store):
    assert store.get_trust("nobody") == pytest.approx(0.5)


def test_positive_interactions_increase_trust(store):
    for _ in range(10):
        store.encode("user_0", "chin_scratch", +0.7)
    trust = store.get_trust("user_0")
    assert trust > 0.5


def test_negative_interactions_decrease_trust(store):
    for _ in range(10):
        store.encode("user_1", "tail_pull", -0.8)
    trust = store.get_trust("user_1")
    assert trust < 0.5


def test_trust_is_bounded(store):
    for _ in range(1000):
        store.encode("user_2", "pet", +1.0)
    trust = store.get_trust("user_2")
    assert 0.0 <= trust <= 1.0


def test_facts_roundtrip(store):
    store.set_fact("owner_name", "Ada")
    assert store.get_fact("owner_name") == "Ada"


def test_missing_fact_returns_none(store):
    assert store.get_fact("nonexistent_key") is None


def test_fact_overwrite(store):
    store.set_fact("greeting", "hello")
    store.set_fact("greeting", "hi there")
    assert store.get_fact("greeting") == "hi there"


def test_recent_episodes(store):
    store.encode("user_3", "pet_head", +0.3)
    store.encode("user_3", "chin_scratch", +0.5)
    episodes = store.get_recent_episodes("user_3", n=5)
    assert len(episodes) == 2
    assert episodes[0].event == "chin_scratch"  # most recent first
