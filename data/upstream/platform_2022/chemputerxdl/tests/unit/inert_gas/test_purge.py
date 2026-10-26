import os
import pytest
from xdl import XDL
from ...utils import generic_chempiler_test

HERE = os.path.abspath(os.path.dirname(__file__))
FILES = os.path.join(HERE, 'files')

@pytest.mark.unit
def test_purge():
    """Test purge step."""
    xdl_f = os.path.join(FILES, 'purge.xdl')
    graph_f = os.path.join(FILES, 'purge_graph.json')
    x = XDL(xdl_f)
    x.prepare_for_execution(graph_f, testing=True)
    for step in x.steps:
        if step.name == 'StartPurge':
            if step.vessel == 'reactor':
                assert step.steps[0].name == 'SwitchArgon'
                assert (step.steps[0].pneumatic_controller
                        == 'pneumatic_controller')
                assert (str(step.steps[0].pneumatic_controller_port)
                        == '2')
            elif step.vessel == 'filter':
                assert step.steps[0].name == 'CConnect'
                assert step.steps[0].from_vessel == 'flask_argon'
                assert step.steps[0].to_vessel == 'filter'

        elif step.name == 'StopPurge':
            if step.vessel == 'reactor':
                assert step.steps[0].name == 'SwitchArgon'
                assert (step.steps[0].pneumatic_controller
                        == 'pneumatic_controller')
                assert (str(step.steps[0].pneumatic_controller_port)
                        == '2')
            elif step.vessel == 'filter':
                assert step.steps[0].name == 'CValveMoveToPosition'
                assert step.steps[0].valve_name == 'inert_gas_valve'
                assert str(step.steps[0].position) == '2'

        elif step.name == 'Purge':
            assert step.steps[0].name == 'StartPurge'
            assert step.steps[1].name == 'Wait'
            assert step.steps[1].time == 5 * 60
            assert step.steps[2].name == 'StopPurge'

    generic_chempiler_test(xdl_f, graph_f)

@pytest.mark.unit
def test_purge_backbone():
    """Test purge step."""
    xdl_f = os.path.join(FILES, 'purge_backbone.xdl')
    graph_f = os.path.join(FILES, 'purge_graph.json')
    x = XDL(xdl_f)
    x.prepare_for_execution(graph_f, testing=True)
    generic_chempiler_test(xdl_f, graph_f)
