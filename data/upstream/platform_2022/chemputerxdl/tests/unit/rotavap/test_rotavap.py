import os
import pytest
import functools

from xdl import XDL
from chemputerxdl.steps import (
    Evaporate,
    Purge,
    Transfer,
    CRotavapAutoEvaporation,
    RotavapStopEverything,
    CTemperatureControllerStop,
    CTemperatureControllerStart,
    HeatChillToTemp,
    Dry,
    CR300RotavapSetManualMode,
    CR300RotavapSetAutoMode,
    EvaporateDynamic,
    CPressureControllerSetPressure,
    CStirringControllerSetSpeed,
    CR300RotavapStartChiller,
    CRotavapLiftDown,
    CRotavapStart,
    Wait,
    CRotavapStop,
    StopHeatChill,
)

from ...utils import generic_chempiler_test, XDLStory
from chemputerxdl.constants import COLLECT_PORT

HERE = os.path.abspath(os.path.dirname(__file__))
FILES = os.path.join(HERE, 'files')
GLOBAL_FILES = os.path.join(HERE, '..', 'files')

@pytest.mark.unit
def test_dissolve_in_rotavap():
    """Test that dissolving a solid in the rotavap works."""
    xdl_f = os.path.join(GLOBAL_FILES, 'dissolve_in_rotavap.xdl')
    graph_f = os.path.join(GLOBAL_FILES, 'bigrig.json')
    generic_chempiler_test(xdl_f, graph_f)

@pytest.mark.unit
def test_wash_in_rotavap():
    """Test that washing a solid in the rotavap works."""
    xdl_f = os.path.join(GLOBAL_FILES, 'wash_in_rotavap.xdl')
    graph_f = os.path.join(GLOBAL_FILES, 'bigrig.json')
    x = XDL(xdl_f)
    for step in x.steps:
        print(step.name, step.properties, '\n')
    generic_chempiler_test(xdl_f, graph_f)

@pytest.mark.unit
def test_rotavap():
    """Test rotavap evaporate step."""
    xdl_f = os.path.join(FILES, 'rotavap.xdl')
    graph_f = os.path.join(GLOBAL_FILES, 'bigrig.json')
    generic_chempiler_test(xdl_f, graph_f)

@pytest.mark.unit
def test_rotavap_auto_mode():
    """Test rotavap auto evaporate mode."""
    xdl_f = os.path.join(FILES, 'rotavap_auto.xdl')
    graph_f = os.path.join(GLOBAL_FILES, 'bigrig.json')
    x = XDL(xdl_f)
    x.prepare_for_execution(graph_f, testing=True)
    for step in x.steps:
        if type(step) == Evaporate:
            assert type(step.steps[-3]) == RotavapStopEverything
            assert type(step.steps[-4]) == CRotavapAutoEvaporation
            assert type(step.steps[-5]) == HeatChillToTemp

            # Check stir speed being passed to all child steps
            target_stir_speed = step.stir_speed
            checked = False
            for step in step.base_steps:
                if 'stir_speed' in step.properties:
                    assert step.stir_speed == target_stir_speed
                    checked = True
            assert checked
            break

    generic_chempiler_test(xdl_f, graph_f)

@pytest.mark.unit
def test_rotavap_child_props():
    """Test rotavap withdraws correct amount after evaporation."""
    xdl_f = os.path.join(FILES, 'rotavap.xdl')
    graph_f = os.path.join(GLOBAL_FILES, 'bigrig.json')
    x = XDL(xdl_f)
    x.prepare_for_execution(graph_f, testing=True)
    for step in x.steps:
        if type(step) == Evaporate:
            # collection_flask_volume in graph
            assert step.steps[-1].volume == 50

            # Check stir speed being passed to all child steps
            target_stir_speed = step.stir_speed
            checked = False
            for step in step.base_steps:
                if 'stir_speed' in step.properties:
                    assert step.stir_speed == target_stir_speed
                    checked = True
            assert checked

# TODO: Upgrade graphml graphs with "temp_sensor" property
# @pytest.mark.unit
def test_rotavap_rotation_speed():
    xdl_f = os.path.join(GLOBAL_FILES, 'alkyl_fluor_step4.xdl')
    graph_f = os.path.join(GLOBAL_FILES, 'alkyl_fluor_step4.graphml')
    x = XDL(xdl_f)
    x.prepare_for_execution(graph_f, testing=True)
    for step in x.base_steps:
        if step.name == 'CRotavapSetRotationSpeed':
            assert step.rotation_speed <= 300

@pytest.mark.unit
def test_rotavap_has_chiller():
    """Test rotavap has a chiller attached."""
    xdl_f = os.path.join(FILES, 'rotavap.xdl')
    graph_f = os.path.join(GLOBAL_FILES, 'bigrig.json')
    x = XDL(xdl_f)
    x.prepare_for_execution(graph_f, testing=True)

    for step in x.steps:
        if type(step) == Evaporate:

            chiller_started, chiller_stopped = False, False
            assert step.chiller
            for substep in step.steps:
                if type(substep) == CTemperatureControllerStart:
                    if substep.temperature_controller == step.chiller:
                        chiller_started = True
                elif type(substep) == CTemperatureControllerStop:
                    if substep.temperature_controller == step.chiller:
                        chiller_stopped = True
            assert chiller_started and chiller_stopped

@pytest.mark.unit
def test_evaporate_purge_mode():
    """Test evaporate purge mode."""
    xdl_f = os.path.join(FILES, 'evaporate_purge_mode.xdl')
    graph_f = os.path.join(GLOBAL_FILES, 'bigrig.json')
    x = XDL(xdl_f)
    purge_step = x.steps[0].steps[0]
    assert type(purge_step) == Purge
    assert purge_step.time == x.steps[0].time
    generic_chempiler_test(xdl_f, graph_f)

@pytest.mark.unit
def test_rotavap_collection_waste_vessel_choice():
    """Test that the waste vessel used to empty the collection flask is the one
    closest to the collection flask, not the one closest to the rotavap
    evaporation port.
    """
    xdl_f = os.path.join(FILES, 'evaporate-orgsyn-v81p0262.xdl')
    graph_f = os.path.join(GLOBAL_FILES, 'orgsyn_v81p0262.json')
    x = XDL(xdl_f)
    x.prepare_for_execution(graph_f, testing=True)
    for step in x.steps:
        if type(step) == Evaporate:
            for substep in step.steps:
                if (type(substep) == Transfer
                        and substep.from_port == COLLECT_PORT):
                    assert substep.to_vessel == 'waste_K'
    generic_chempiler_test(xdl_f, graph_f)

@pytest.mark.unit
def test_evaporate_in_flask():
    """Test that evaporation in a flask without a rotavap works."""
    xdl_f = os.path.join(FILES, 'evaporate-in-flask.xdl')
    graph_f = os.path.join(FILES, 'evaporate-in-flask-graph.json')
    x = XDL(xdl_f)
    x.prepare_for_execution(graph_f, testing=True)
    generic_chempiler_test(xdl_f, graph_f)


# XDLStory using bigrig graph and unit test mark
Jones_oxidation_story = functools.partial(
    XDLStory,
    graph=os.path.join(FILES, 'Jones_oxidation.json'),
    mark=pytest.mark.unit
)

test_story_R300_manual_mode = Jones_oxidation_story(
    name='Evaporation in manual mode with R300 rotavap',
    start=Evaporate(
        vessel='rotavap',
        temp="50 °C",
        mode='manual',
        pressure='50 mbar'
    ),
    substeps=[
        CR300RotavapSetManualMode(rotavap_name='rotavap'),
        CPressureControllerSetPressure(
            pressure_controller='rotavap', pressure='50 mbar'),
        CStirringControllerSetSpeed(
            stirring_controller='rotavap', stir_speed='150'),
        CR300RotavapStartChiller(rotavap_name='rotavap'),
        HeatChillToTemp(vessel='rotavap', temp="50 °C", stir_speed="150 rpm"),
        CRotavapLiftDown(rotavap_name='rotavap'),
        CRotavapStart(rotavap_name='rotavap'),
        Wait(time="2 h"),
        CRotavapStop(rotavap_name='rotavap'),
        StopHeatChill(vessel='rotavap')
    ],
    not_substeps=[
        CR300RotavapSetAutoMode(rotavap_name='rotavap'),
        EvaporateDynamic(vessel='rotavap', max_time="2 h")
    ]
)

test_story_R300_auto_mode = Jones_oxidation_story(
    name='Evaporation in auto mode with R300 rotavap',
    start=Evaporate(
        vessel='rotavap',
        temp="50 °C",
        mode='auto',
        pressure='50 mbar'
    ),
    substeps=[
        CR300RotavapSetAutoMode(rotavap_name='rotavap'),
        CStirringControllerSetSpeed(
            stirring_controller='rotavap', stir_speed='150'),
        CR300RotavapStartChiller(rotavap_name='rotavap'),
        HeatChillToTemp(vessel='rotavap', temp="50 °C", stir_speed="150 rpm"),
        CRotavapLiftDown(rotavap_name='rotavap'),
        CRotavapStart(rotavap_name='rotavap'),
        EvaporateDynamic(vessel='rotavap', max_time="2 h"),
        CRotavapStop(rotavap_name='rotavap'),
        StopHeatChill(vessel='rotavap')
    ],
    not_substeps=[
        CR300RotavapSetManualMode(rotavap_name='rotavap'),
        CPressureControllerSetPressure(
            pressure_controller='rotavap', pressure='50 mbar'),
        Wait(time="2 h")
    ]
)

test_story_R300_dry = Jones_oxidation_story(
    name='Dry with R300 rotavap',
    start=Dry(
        vessel='rotavap',
        temp="50 °C",
        pressure='50 mbar',
        time="30 min"
    ),
    substeps=[
        CR300RotavapSetManualMode(rotavap_name='rotavap'),
        CPressureControllerSetPressure(
            pressure_controller='rotavap', pressure='50 mbar'),

        CRotavapStart(rotavap_name='rotavap'),
        Wait(time="30 min"),
        CRotavapStop(rotavap_name='rotavap'),
    ]
)
