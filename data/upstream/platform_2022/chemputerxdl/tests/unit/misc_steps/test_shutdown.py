import pytest
import os
from xdl import XDL
from chemputerxdl.steps import Shutdown

HERE = os.path.abspath(os.path.dirname(__file__))
FILES = os.path.join(HERE, 'files')
INTEGRATION_FILES = os.path.join(os.path.dirname(HERE), 'integration', 'files')
GLOBAL_FILES = os.path.join(HERE, '..', 'files')


@pytest.mark.unit
def test_xdl_ends_with_shutdown():
    x = XDL(os.path.join(GLOBAL_FILES, "dissolve_in_rotavap.xdl"))
    graph_f = os.path.join(GLOBAL_FILES, "bigrig.json")
    x.prepare_for_execution(graph_f, testing=True)
    assert type(x.steps[-1]) == Shutdown
    shutdown = x.steps[-1]

    assert len(shutdown.steps) == 18

    chiller_shutdown = False
    flask_chiller_shutdown = False

    stirrer_separator_shutdown = False
    stirrer_filter_shutdown = False
    stirrer_flask_shutdown = False
    stirrer_reactor_shutdown = False

    vacuum_rotavap_stopped = False
    vacuum_rotavap_vented = False
    vacuum_filter_stopped = False
    vacuum_filter_vented = False
    vacuum_reactor_stopped = False
    vacuum_reactor_vented = False

    rotavap_up = False
    rotavap_stopped_rotation = False
    rotavap_stopped_heating = False

    hotplate_reactor_heating_shutdown = False
    hotplate_reactor_stirring_shutdown = False

    for step in shutdown.steps:
        if step.name == 'CTemperatureControllerStop':
            if step.temperature_controller == 'filter_chiller':
                chiller_shutdown = True

            elif step.temperature_controller == 'flask_chiller':
                flask_chiller_shutdown = True

            elif step.temperature_controller == 'rotavap':
                rotavap_stopped_heating = True

            elif step.temperature_controller == 'reactor_heater':
                hotplate_reactor_heating_shutdown = True

        elif step.name == 'CPressureControllerStop':
            if step.pressure_controller == 'vacuum_device':
                vacuum_filter_stopped = True

            elif step.pressure_controller == 'vacuum_rotavap':
                vacuum_rotavap_stopped = True

            elif step.pressure_controller == 'vacuum_reactor_device':
                vacuum_reactor_stopped = True

        elif step.name == 'VentVacuum':
            if step.vessel == 'vacuum_device':
                vacuum_filter_vented = True

            elif step.vessel == 'vacuum_rotavap':
                vacuum_rotavap_vented = True

            elif step.vessel == 'vacuum_reactor_device':
                vacuum_reactor_vented = True

        elif step.name == 'CStirringControllerStop':
            if step.stirring_controller == 'stirrer':
                stirrer_filter_shutdown = True

            elif step.stirring_controller == 'stirrer_separator':
                stirrer_separator_shutdown = True

            elif step.stirring_controller == 'stirrer_reactor':
                stirrer_reactor_shutdown = True

            elif step.stirring_controller == 'flask_stirrer':
                stirrer_flask_shutdown = True

            elif step.stirring_controller == 'reactor_heater':
                hotplate_reactor_stirring_shutdown = True

            elif step.stirring_controller == 'rotavap':
                rotavap_stopped_rotation = True

        elif step.name == 'CRotavapLiftUp':
            if step.rotavap_name == 'rotavap':
                rotavap_up = True

    assert chiller_shutdown
    assert flask_chiller_shutdown

    assert stirrer_separator_shutdown
    assert stirrer_filter_shutdown
    assert stirrer_flask_shutdown
    assert stirrer_reactor_shutdown

    assert vacuum_rotavap_stopped
    assert vacuum_rotavap_vented
    assert vacuum_filter_stopped
    assert vacuum_filter_vented
    assert vacuum_reactor_stopped
    assert vacuum_reactor_vented

    assert rotavap_up
    assert rotavap_stopped_rotation
    assert rotavap_stopped_heating

    assert hotplate_reactor_heating_shutdown
    assert hotplate_reactor_stirring_shutdown
