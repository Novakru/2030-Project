import os
import pytest

from xdl import XDL

from ...utils import generic_chempiler_test

HERE = os.path.abspath(os.path.dirname(__file__))
FILES = os.path.join(HERE, 'files')

# Correct properties to check
CORRECT_BUBBLE_SENSOR = 'bubble'
CORRECT_ON_CONTINUE_SEQUENCE_LENGTH = 4
CORRECT_ASPIRATION_PUMP = 'pump_H'
CORRECT_ASPIRATION_PUMP_MAX_VOLUME = 25.0
DYNAMIC_TRANSFER_STEP_NAME = 'DynamicTransfer'


@pytest.mark.unit
def test_dynamic_transfer():
    """ Test DynamicTransfer step.

    Not really informative, since in simulation DynamicTransfer falls back to
    normal Transfer Step.
    """

    xdl_f = os.path.join(FILES, 'dynamic_transfer.xdl')
    graph_f = os.path.join(FILES, 'graph_bubble.json')
    generic_chempiler_test(xdl_f, graph_f)

@pytest.mark.unit
def test_dynamic_transfer_properties():
    """ Test DynamicTransfer Step properties.

    Tests if procedure "compiled" correctly.
    """
    xdl_f = os.path.join(FILES, 'dynamic_transfer.xdl')
    graph_f = os.path.join(FILES, 'graph_bubble.json')

    x = XDL(xdl_f)
    x.prepare_for_execution(graph_f, testing=True)

    for step in x.steps:
        if step.name == DYNAMIC_TRANSFER_STEP_NAME:
            dynamic_transfer_step = step

    assert dynamic_transfer_step

    # Checking compiled properties
    assert dynamic_transfer_step.bubble_sensor == CORRECT_BUBBLE_SENSOR
    assert dynamic_transfer_step.aspiration_pump == CORRECT_ASPIRATION_PUMP
    assert (
        dynamic_transfer_step.aspiration_pump_max_volume
        == CORRECT_ASPIRATION_PUMP_MAX_VOLUME
    )

    # Checking dynamic on_continue methods
    on_continue_steps = dynamic_transfer_step.on_continue()
    assert on_continue_steps
    # Should contain InvokeBubbleSensor, CMove and EndBubbleSensor
    assert len(on_continue_steps) == CORRECT_ON_CONTINUE_SEQUENCE_LENGTH
