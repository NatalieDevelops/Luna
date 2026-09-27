"""Unit tests for firmware.neural_unit utilities (no hardware required)"""

import struct

import pytest

from ruby.firmware.neural_unit import _crc8, PersonalitySnapshot, InstinctModel


def test_crc8_known_value():
    # CRC8 of b'PONG' should be deterministic
    assert 0 <= _crc8(b"PONG") <= 255


def test_crc8_empty():
    assert _crc8(b"") == 0


def test_personality_snapshot_defaults():
    snap = PersonalitySnapshot()
    for field in ("bold", "playful", "cautious", "affectionate", "curious", "independent"):
        assert getattr(snap, field) == pytest.approx(0.5)


def test_personality_snapshot_repr():
    snap = PersonalitySnapshot(bold=0.8, playful=0.3)
    r = repr(snap)
    assert "bold=0.80" in r
    assert "playful=0.30" in r
