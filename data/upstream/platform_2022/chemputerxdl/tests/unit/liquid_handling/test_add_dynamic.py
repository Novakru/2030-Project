import os
import pytest

from xdl import XDL

from ...utils import generic_chempiler_test

HERE = os.path.abspath(os.path.dirname(__file__))
FILES = os.path.join(HERE, 'files')

# Correct properties to check
CORRECT_RTD_SENSOR = 'rtd'
CORRECT_ASPIRATION_PUMP = 'pump_3'
CORRECT_ASPIRATION_PUMP_MAX_VOLUME = 5.0
DYNAMIC_ADD_STEP_NAME = 'AddDynamic'

@pytest.mark.unit
def test_dynamic_add():
    """ Test DynamicAdd step."""

    xdl_f = os.path.join(FILES, 'dynamic_add.xdl')
    graph_f = os.path.join(FILES, 'graph_rtd.json')
    generic_chempiler_test(xdl_f, graph_f)

@pytest.mark.unit
def test_dynamic_add_properties():
    """ Test DynamicAdd Step properties.

    Tests if procedure "compiled" correctly.
    """
    xdl_f = os.path.join(FILES, 'dynamic_add.xdl')
    graph_f = os.path.join(FILES, 'graph_rtd.json')

    x = XDL(xdl_f)
    x.prepare_for_execution(graph_f, testing=True)

    for step in x.steps:
        if step.name == DYNAMIC_ADD_STEP_NAME:
            dynamic_add_step = step

    assert dynamic_add_step

    # Checking compiled properties
    assert dynamic_add_step.sensor == CORRECT_RTD_SENSOR
    assert dynamic_add_step.aspiration_pump == CORRECT_ASPIRATION_PUMP
    assert (
        dynamic_add_step.aspiration_pump_max_volume
        == CORRECT_ASPIRATION_PUMP_MAX_VOLUME
    )
