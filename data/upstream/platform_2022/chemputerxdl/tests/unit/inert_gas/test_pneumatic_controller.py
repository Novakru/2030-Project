import os
import functools
import pytest
from xdl import XDL
from chemputerxdl.steps import (
    CConnect, StartPurge, StopPurge, SwitchArgon, CSwitchArgon,
    CValveMoveToPosition, EvacuateAndRefill, SwitchVacuum, CSwitchVacuum,
    ApplyVacuum
)
from ...utils import XDLStory, generic_chempiler_test

HERE = os.path.abspath(os.path.dirname(__file__))
FILES = os.path.join(HERE, 'files')

@pytest.mark.unit
def test_pneumatic_controller():
    """Test pneumatic controller works correctly."""
    xdl_f = os.path.join(FILES, 'pneumatic_controller.xdl')
    graph_f = os.path.join(FILES, 'pneumatic_controller.json')
    x = XDL(xdl_f)
    x.prepare_for_execution(graph_f, testing=True)

    # Ignores the shutdown at the end
    check_steps = x.steps[:-1]
    for step in check_steps:
        assert step.pneumatic_controller == 'pneumatic_controller'

        if step.vessel == 'flask':
            assert str(step.pneumatic_controller_port) == '2'

        elif step.vessel == 'filter':

            if step.port == 'bottom':
                assert str(step.pneumatic_controller_port) == '1'

            elif step.port == 'top':
                assert str(step.pneumatic_controller_port) == '3'

    generic_chempiler_test(xdl_f, graph_f)

@pytest.mark.unit
def test_pneumatic_controller_ports():
    """This file was causing an error, see issue #22."""
    xdl_f = os.path.join(FILES, 'MIDA-Deprotection.xdl')
    graph_f = os.path.join(FILES, 'MIDA-Deprotection.json')
    generic_chempiler_test(xdl_f, graph_f)


pneumatic_controller_through_valve_story = functools.partial(
    XDLStory,
    mark=pytest.mark.unit,
    graph=os.path.join(
        HERE, 'files', 'pneumatic_controller_through_valve.json'),
)

pneumatic_controller_direct_story = functools.partial(
    XDLStory,
    mark=pytest.mark.unit,
    graph=os.path.join(
        HERE, 'files', 'pneumatic_controller_direct.json'),
)

test_story_start_purge_pneumatic_controller_through_valve =\
    pneumatic_controller_through_valve_story(
        name='Use StartPurge with pneumatic controller connected through valve.',  # noqa: E501
        start=StartPurge(vessel='filter'),
        substeps=[
            SwitchArgon(
                vessel='filter',
                pressure='high',
                vacuum_valve='Valve_8',
                after_switch_wait=None
            ),
            CConnect(
                from_vessel='pneumatic_controller',
                to_vessel='filter',
            ),
            CSwitchArgon(
                pneumatic_controller='pneumatic_controller',
                port=5,
                pressure='high',
                after_switch_wait=None
            )
        ],
    )

test_story_stop_purge_pneumatic_controller_through_valve =\
    pneumatic_controller_through_valve_story(
        name='Use StopPurge with pneumatic controller connected through valve.',
        start=StopPurge(vessel='filter'),
        substeps=[
            SwitchArgon(
                vessel='filter',
                pressure='low',
                after_switch_wait=None
            ),
            CSwitchArgon(
                pneumatic_controller='pneumatic_controller',
                port=5,
                pressure='low'
            ),
            CValveMoveToPosition('Valve_8', position=0)
        ],
    )

test_story_evacuate_pneumatic_controller_through_valve =\
    pneumatic_controller_through_valve_story(
        name='Use EvacuateAndRefill with pneumatic controller connected through valve.',  # noqa: E501
        start=EvacuateAndRefill(vessel='filter'),
        substeps=[
            SwitchArgon(
                vessel='filter',
                pressure='high',
                vacuum_valve='Valve_8',
                after_switch_wait=60,
            ),
            SwitchVacuum(
                vessel='filter',
                vacuum_valve='Valve_8',
                after_switch_wait=60,
            ),
            CConnect(
                from_vessel='pneumatic_controller',
                to_vessel='filter',
            ),
            CSwitchArgon(
                pneumatic_controller='pneumatic_controller',
                port=5,
                pressure='high',
            ),
            CSwitchVacuum(
                pneumatic_controller='pneumatic_controller',
                port=5,
            )
        ],
    )

test_story_apply_vacuum_pneumatic_controller_through_valve =\
    pneumatic_controller_through_valve_story(
        name='Use ApplyVacuum with pneumatic controller connected through valve.',  # noqa: E501
        start=ApplyVacuum(vessel='filter', time='1 min'),
        substeps=[
            SwitchVacuum(
                vessel='filter',
                vacuum_valve='Valve_8',
            ),
            CConnect(
                from_vessel='pneumatic_controller',
                to_vessel='filter',
            ),
            CSwitchVacuum(
                pneumatic_controller='pneumatic_controller',
                port=5,
            )
        ],
    )

test_story_apply_vacuum_pneumatic_controller_direct =\
    pneumatic_controller_direct_story(
        name='Use ApplyVacuum with pneumatic controller connected directly.',
        start=ApplyVacuum(vessel='filter', time='1 min'),
        substeps=[
            SwitchVacuum(
                vessel='filter',
                vacuum_valve='Valve_8',
            ),
            CSwitchVacuum(
                pneumatic_controller='pneumatic_controller',
                port=5,
            )
        ],
        not_substeps=[
            CConnect(
                from_vessel='pneumatic_controller',
                to_vessel='filter',
            ),
        ]
    )

test_story_start_purge_pneumatic_controller_direct =\
    pneumatic_controller_direct_story(
        name='Use StartPurge with pneumatic controller connected directly.',  # noqa: E501
        start=StartPurge(vessel='filter'),
        substeps=[
            SwitchArgon(
                vessel='filter',
                pressure='high',
                vacuum_valve='Valve_8',
                after_switch_wait=None
            ),
            CSwitchArgon(
                pneumatic_controller='pneumatic_controller',
                port=5,
                pressure='high',
                after_switch_wait=None
            )
        ],
        not_substeps=[
            CConnect(
                from_vessel='pneumatic_controller',
                to_vessel='filter',
            ),
        ]
    )

test_story_stop_purge_pneumatic_controller_directly =\
    pneumatic_controller_direct_story(
        name='Use StopPurge with pneumatic controller connected directly.',
        start=StopPurge(vessel='filter'),
        substeps=[
            SwitchArgon(
                vessel='filter',
                pressure='low',
                after_switch_wait=None
            ),
            CSwitchArgon(
                pneumatic_controller='pneumatic_controller',
                port=5,
                pressure='low'
            ),
        ],
        not_substeps=[
            CValveMoveToPosition('Valve_8', position=0)
        ]
    )

test_story_evacuate_pneumatic_controller_direct =\
    pneumatic_controller_direct_story(
        name='Use EvacuateAndRefill with pneumatic controller connected directly.',  # noqa: E501
        start=EvacuateAndRefill(vessel='filter'),
        substeps=[
            SwitchArgon(
                vessel='filter',
                pressure='high',
                after_switch_wait=60,
            ),
            SwitchVacuum(
                vessel='filter',
                after_switch_wait=60,
            ),
            CSwitchArgon(
                pneumatic_controller='pneumatic_controller',
                port=5,
                pressure='high',
            ),
            CSwitchVacuum(
                pneumatic_controller='pneumatic_controller',
                port=5,
            )
        ],
        not_substeps=[
            CConnect(
                from_vessel='pneumatic_controller',
                to_vessel='filter',
            ),
        ]
    )
