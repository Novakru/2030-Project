import os
import pytest
from xdl import XDL
from chemputerxdl.steps.steps_utility.separate_phases import (
    SEPARATION_DEFAULT_END_PUMP_SPEED_CART,
    SEPARATION_DEFAULT_END_PUMP_SPEED
)
from xdl.errors import XDLError
from ...utils import generic_chempiler_test

HERE = os.path.abspath(os.path.dirname(__file__))
FILES = os.path.join(HERE, 'files')
GLOBAL_FILES = os.path.join(HERE, '..', 'files')

@pytest.mark.unit
def test_separate_phases():
    """Test SeparatePhases step."""
    xdl_f = os.path.join(FILES, 'separate_phases.xdl')
    graph_f = os.path.join(GLOBAL_FILES, 'bigrig.json')
    generic_chempiler_test(xdl_f, graph_f)

@pytest.mark.unit
def test_separate_phases_retry():
    """To use this test make on_conductivity_sensor_reading set
    self.done = False during simulation and see if the retries happen
    successfully."""
    xdl_f = os.path.join(FILES, 'separate_phases_retry.xdl')
    graph_f = os.path.join(GLOBAL_FILES, 'bigrig.json')
    generic_chempiler_test(xdl_f, graph_f)

@pytest.mark.unit
def test_separate_phases_through_speed():
    """Test SeparatePhases different speed if going through cartridge."""
    xdl_f = os.path.join(FILES, 'separate_phases.xdl')
    graph_f = os.path.join(GLOBAL_FILES, 'bigrig.json')
    x = XDL(xdl_f)
    x.prepare_for_execution(graph_f, testing=True)
    for step in x.steps:
        if step.name == 'SeparatePhases':

            steps = ([
                step.prime_sensor_step(),
                step.lower_phase_separation_pump_dispense_step()
            ] + step.upper_phase_withdraw_step()
              + step.dead_volume_withdraw_step())

            assert steps

            for substep in steps:
                if substep.name == 'Transfer':
                    if substep.through:
                        assert (substep.dispense_speed
                                == SEPARATION_DEFAULT_END_PUMP_SPEED_CART)
                    else:
                        assert (substep.dispense_speed
                                == SEPARATION_DEFAULT_END_PUMP_SPEED)

@pytest.mark.unit
def test_separate_phases_both_phases_to_same_vessel():
    xdl_f = os.path.join(FILES, 'separate_phases_bad.xdl')
    graph_f = os.path.join(GLOBAL_FILES, 'bigrig.json')
    with pytest.raises(XDLError):
        generic_chempiler_test(xdl_f, graph_f)
