import pytest
import logging

@pytest.mark.hardware
def test_write_digital(ramps, caplog):

    caplog.set_level(logging.DEBUG)
    ramps.write_digital("LED", 0)
    assert "set_level(0)" in caplog.text
    caplog.clear()
    ramps.write_digital("LED", 1)
    assert "set_level(1)" in caplog.text
    caplog.clear()


@pytest.mark.hardware
def test_read_digital(ramps, caplog):

    caplog.set_level(logging.DEBUG)
    if ramps._simulation is True:
        assert ramps.read_digital("Servo1Write") is None
    else:
        assert ramps.read_digital("Servo1Write") in [0, 1]
    assert "get_state()" in caplog.text
    caplog.clear()


@pytest.mark.hardware
@pytest.mark.parametrize("value", [0, 128, 255])
def test_write_analog(ramps, caplog, value):

    caplog.set_level(logging.DEBUG)
    ramps.write_analog("Heater0", value)
    assert f"set_pwm_value({value})" in caplog.text
    caplog.clear()


@pytest.mark.hardware
def test_read_analog(ramps, caplog):

    caplog.set_level(logging.DEBUG)
    if ramps._simulation is True:
        assert ramps.read_analog("Servo1Read") is None
    else:
        assert ramps.read_analog("Servo1Read") in [0, 255]
    assert "get_level()" in caplog.text
