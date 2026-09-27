"""Unit tests for tactile.sensefur zone mapping and event logic"""

import pytest

from ruby.tactile.sensefur import _index_to_zone, ZONE_MAP


def test_all_128_fibers_have_zones():
    for i in range(128):
        zone = _index_to_zone(i)
        assert zone != "unknown", f"fiber {i} has no zone"


def test_zone_map_covers_all_fibers():
    covered = set()
    for zone, (lo, hi) in ZONE_MAP.items():
        covered.update(range(lo, hi + 1))
    assert covered == set(range(128))


def test_zone_boundaries():
    assert _index_to_zone(0)   == "head"
    assert _index_to_zone(31)  == "head"
    assert _index_to_zone(32)  == "back"
    assert _index_to_zone(63)  == "back"
    assert _index_to_zone(64)  == "belly"
    assert _index_to_zone(127) == "paw_rr"
