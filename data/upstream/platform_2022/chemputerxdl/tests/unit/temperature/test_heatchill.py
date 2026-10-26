import os
import pytest
import functools

from ...utils import (
    generic_chempiler_test,
    XDLStory
)
from xdl import XDL
from chemputerxdl.constants import (
    CHILLER_MIN_TEMP,
    HEATER_MAX_TEMP
)
from chemputerxdl.steps import (
    CTemperatureControllerSetTemp,
    HeatChill,
    HeatChillToTemp,
    CRotavapLiftDown,
    CRotavapLiftUp
)

HERE = os.path.abspath(os.path.dirname(__file__))
FILES = os.path.join(HERE, 'files')
GLOBAL_FILES = os.path.join(HERE, '..', 'files')

@pytest.mark.unit
def test_start_stop_heatchill():
    """Test that StartHeatChill and StopHeatChill work."""
    xdl_f = os.path.join(FILES, 'heatchill.xdl')
    graph_f = os.path.join(GLOBAL_FILES, 'bigrig.json')
    x = XDL(xdl_f)
    x.prepare_for_execution(graph_f, testing=True)
    generic_chempiler_test(xdl_f, graph_f)

@pytest.mark.unit
def test_inactive_heatchill():
    xdl_f = os.path.join(FILES, 'inactive_heatchill.xdl')
    graph_f = os.path.join(GLOBAL_FILES, 'bigrig.json')
    x = XDL(xdl_f)
    x.prepare_for_execution(graph_f, testing=True)
    generic_chempiler_test(xdl_f, graph_f)

@pytest.mark.unit
def test_heatchill_return_to_rt():
    xdl_f = os.path.join(FILES, 'heatchill_return_to_rt.xdl')
    graph_f = os.path.join(FILES, 'heatchill_return_to_rt.json')
    x = XDL(xdl_f)
    x.prepare_for_execution(graph_f, testing=True)
    generic_chempiler_test(xdl_f, graph_f)

@pytest.mark.unit
def test_heatchill_reactor_with_heater_and_chiller():
    xdl_f = os.path.join(FILES, 'heater_chiller_reactor.xdl')
    graph_f = os.path.join(FILES, 'heater_chiller_reactor.json')
    x = XDL(xdl_f)
    x.prepare_for_execution(graph_f, testing=True)
    assert len([
        step
        for step in x.base_steps
        if type(step) == CTemperatureControllerSetTemp
    ]) == 9
    for step in x.base_steps:
        if type(step) == CTemperatureControllerSetTemp:
            assert CHILLER_MIN_TEMP < step.temp < HEATER_MAX_TEMP
    generic_chempiler_test(xdl_f, graph_f)

@pytest.mark.unit
def test_heatchill_reactor_hotplate_chiller_selection():
    """Make sure heat chill steps choose the correct one of hotplate or chiller
    when both are available.
    """
    xdl_f = os.path.join(FILES, 'heatchill_hotplate_chiller_selection.xdl')
    graph_f = os.path.join(FILES, 'reactor_with_hotplate_and_chiller.json')
    x = XDL(xdl_f)
    x.prepare_for_execution(graph_f, testing=True)
    for step in x.steps:
        if 'temp' in step.properties:
            if step.temp < 18:
                assert step.temperature_controller == 'chiller'
            elif step.temp > 150:
                assert step.temperature_controller == 'hotplate'

# XDLStory using bigrig graph and unit test mark


orgsyn_v81p0262_story = functools.partial(
    XDLStory,
    graph=os.path.join(GLOBAL_FILES, 'orgsyn_v81p0262.json'),
    mark=pytest.mark.unit
)


test_story_rotavap_lift_down_up_heatchill = orgsyn_v81p0262_story(
    name='HeatChill in rotavap should start with liftdown and end with liftup',
    start=HeatChill(
        vessel='rotavap',
        temp=50,
        time=120,
    ),
    substeps=[
        CRotavapLiftDown(rotavap_name='rotavap'),
        HeatChillToTemp(vessel='rotavap', temp=50),
        CRotavapLiftUp(rotavap_name='rotavap'),
    ],
)
