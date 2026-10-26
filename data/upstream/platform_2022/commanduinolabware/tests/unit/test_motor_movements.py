import pytest
import logging
import time

@pytest.mark.hardware
@pytest.mark.parametrize("increment, n_turns, wait", [(6400, 1, True), (3200, 8, False)])
def test_turn_motor(ramps, caplog, increment, n_turns, wait):

    if ramps._simulation is True:
        caplog.set_level(logging.INFO)
        ramps.turn_motor(motor="wheel", increment=increment, n_turns=n_turns, wait=wait)
        assert f"move({increment},wait={wait})" in caplog.text
        # Should output one "INFO move(...)" line per turn
        assert len(caplog.messages) == len([m for m in caplog.messages if "move" in m])


@pytest.mark.hardware
@pytest.mark.parametrize("steps, wait", [(800, True), (16328, False)])
def test_move_motor(ramps, caplog, steps, wait):

    if ramps._simulation is True:
        caplog.set_level(logging.INFO)
        ramps.move_motor(motor="wheel", steps=steps, wait=wait)
        assert f"move({steps},wait={wait})" in caplog.text
        # Should output only one "INFO" line
        assert len(caplog.messages) == len([m for m in caplog.messages if "move" in m])


@pytest.mark.hardware
@pytest.mark.parametrize("position, wait", [(800, True), (16328, False)])
def test_move_motor_to_position(ramps, caplog, position, wait):

    if ramps._simulation is True:
        caplog.set_level(logging.INFO)
        ramps.move_motor_to_position(motor="wheel", position=position, wait=wait)
        assert f"move_to({position},wait={wait})" in caplog.text
        # Should output only one "INFO" line
        assert len(caplog.messages) == len([m for m in caplog.messages if "move_to" in m])


@pytest.mark.hardware
def test_home_motor(ramps, caplog):

    if ramps._simulation is True:
        caplog.set_level(logging.INFO)
        ramps.home_motor(motor="wheel")
        assert f"home(wait=True)" in caplog.text
        # Should output only one "INFO" line
        assert len(caplog.messages) == len([m for m in caplog.messages if "home" in m])


@pytest.mark.hardware
@pytest.mark.parametrize("duration", [0.1, 0.5, 1, 2])
def test_run_motor(ramps, duration):

    start = time.time()
    ramps.run_motor("wheel", duration)
    stop = time.time()
    assert stop >= start + duration


@pytest.mark.hardware
@pytest.mark.parametrize("speed", [0, 500, 2000])
def test_set_motor_speed(ramps, caplog, speed):

    if ramps._simulation is True:
        caplog.set_level(logging.DEBUG)
        ramps.set_motor_speed(motor="wheel", speed=speed)
        assert f"set_speed({speed})" in caplog.text
        assert f"set_running_speed({speed})" in caplog.text
