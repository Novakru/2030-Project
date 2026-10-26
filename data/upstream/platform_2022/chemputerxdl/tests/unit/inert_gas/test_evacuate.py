import os
import pytest
from ...utils import generic_chempiler_test, test_step
from xdl import XDL
from chemputerxdl.steps import (
    EvacuateAndRefill,
    CConnect,
    Wait,
    StartVacuum,
    StopVacuum,
    SwitchArgon,
    SwitchVacuum
)
from xdl.steps import Repeat

HERE = os.path.abspath(os.path.dirname(__file__))
FILES = os.path.join(HERE, 'files')
GLOBAL_FILES = os.path.join(HERE, '..', 'files')

correct_steps = [
    (CConnect, {'from_vessel': 'filter', 'to_vessel': 'vacuum_flask'}),
    (Wait, {'time': 60}),
    (CConnect, {'from_vessel': 'flask_nitrogen', 'to_vessel': 'filter'}),
    (Wait, {'time': 60}),
]

@pytest.mark.unit
def test_evacuate():
    xdl_f = os.path.join(FILES, 'evacuate.xdl')
    graph_f = os.path.join(GLOBAL_FILES, 'bigrig.json')
    generic_chempiler_test(xdl_f, graph_f)
    x = XDL(xdl_f)
    x.prepare_for_execution(graph_f, testing=True)
    for step in x.steps:
        if type(step) == EvacuateAndRefill:
            assert len(step.steps) == 7
            assert type(step.steps[0]) == StartVacuum
            assert step.steps[0].vessel == 'vacuum_flask'
            assert type(step.steps[1]) == CConnect
            assert type(step.steps[2]) == Wait
            assert step.steps[2].time == 120
            assert type(step.steps[3]) == CConnect
            assert type(step.steps[4]) == Wait
            assert type(step.steps[-2]) == Repeat
            assert type(step.steps[-1]) == StopVacuum
            assert step.steps[-1].vessel == 'vacuum_flask'
            assert (
                step.steps[-2].repeats
                == EvacuateAndRefill.DEFAULT_PROPS['repeats'] - 1
            )

            for i, substep in enumerate(step.steps[-2].children):
                test_step(substep, correct_steps[i])

@pytest.mark.unit
def test_evacuate_pneumatic_controller():
    xdl_f = os.path.join(FILES, 'evacuate.xdl')
    graph_f = os.path.join(FILES, 'pneumatic_controller.json')
    x = XDL(xdl_f)
    x.prepare_for_execution(graph_f, testing=True)
    for step in x.steps:
        if type(step) == EvacuateAndRefill:
            assert len(step.steps) == 2
            assert type(step.steps[0]) == Repeat
            assert len(step.steps[0].children) == 2
            vacuum = step.steps[0].children[0]
            argon = step.steps[0].children[1]
            assert type(vacuum) == SwitchVacuum
            assert vacuum.vessel == step.vessel
            assert type(argon) == SwitchArgon
            assert argon.vessel == step.vessel
            assert argon.pressure == 'high'
            assert type(step.steps[1]) == SwitchArgon
            assert step.steps[1].vessel == step.vessel
            assert step.steps[1].pressure == 'low'
