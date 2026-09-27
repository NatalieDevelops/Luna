"""
tests/integration/test_full_pipeline.py

Integration tests: require actual hardware connected.
Run with: pytest tests/integration/ --hardware

Skip automatically if --hardware flag not passed.
"""

import pytest


def pytest_addoption(parser):
    parser.addoption("--hardware", action="store_true", default=False)


@pytest.fixture
def hardware_required(request):
    if not request.config.getoption("--hardware"):
        pytest.skip("requires --hardware flag")


def test_neural_unit_ping(hardware_required):
    from firmware import NeuralUnit
    with NeuralUnit(port="/dev/ttyUSB0") as unit:
        info = unit.info()
        assert info.firmware_version != ""
        assert info.temp_c < 80.0


def test_sensefur_i2c_present(hardware_required):
    import smbus2
    bus = smbus2.SMBus(1)
    try:
        status = bus.read_byte_data(0x48, 0xFE)
        assert status != 0xFF
    finally:
        bus.close()


def test_purrsynth_ping(hardware_required):
    from hardware.audio import PurrSynth
    ps = PurrSynth(port="/dev/ttyUSB1")
    assert ps._serial is not None
    ps.close()
