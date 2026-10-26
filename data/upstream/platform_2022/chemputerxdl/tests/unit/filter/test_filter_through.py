import os
import pytest
from ...utils import generic_chempiler_test
from xdl import XDL
from xdl.errors import XDLError
from chemputerxdl.steps import FilterThrough, CMove

HERE = os.path.abspath(os.path.dirname(__file__))
FILES = os.path.join(HERE, 'files')
GLOBAL_FILES = os.path.join(HERE, '..', 'files')

@pytest.mark.unit
def test_filter_through():
    """Test that dissolving a solid in the rotavap works."""
    xdl_f = os.path.join(FILES, 'filter_through.xdl')
    graph_f = os.path.join(GLOBAL_FILES, 'bigrig.json')
    generic_chempiler_test(xdl_f, graph_f)

@pytest.mark.unit
def test_dissolve_speed():
    """Test that dissolving a solid has variable speed."""
    xdl_f = os.path.join(FILES, 'filter_through_speed.xdl')
    graph_f = os.path.join(GLOBAL_FILES, 'bigrig.json')
    generic_chempiler_test(xdl_f, graph_f)
    x = XDL(xdl_f)
    x.prepare_for_execution(graph_f, interactive=False)
    for step in x.steps:
        if step.name == "Dissolve":
            for substep in step.steps:
                if substep.name == "Add":
                    assert substep.move_speed == 10
                    assert substep.aspiration_speed == 20
                    assert substep.dispense_speed == 30

@pytest.mark.unit
def test_filter_through_buffer_flask():
    """Test that dissolving a solid in the rotavap works."""
    xdl_f = os.path.join(FILES, 'filter_through_buffer_flask.xdl')
    graph_f = os.path.join(FILES, 'bigrig_modified_filter_through.json')
    x = XDL(xdl_f)
    x.prepare_for_execution(graph_f, interactive=False)
    for step in x.steps:
        if type(step) == FilterThrough:
            assert step.buffer_flask == 'buffer_flask2'
            last_transfer = step.steps[-1]
            assert last_transfer.from_vessel == 'buffer_flask2'
            assert last_transfer.to_vessel == 'rotavap'
    generic_chempiler_test(xdl_f, graph_f)

@pytest.mark.unit
def test_filter_eluting_with_more_than_from_vessel_max_volume():
    xdl_f = os.path.join(
        FILES, 'filter_through_elute_more_than_from_vessel_max_volume.xdl')
    graph_f = os.path.join(GLOBAL_FILES, 'bigrig.json')
    x = XDL(xdl_f)
    x.prepare_for_execution(graph_f, interactive=False)
    tests = [
        (10, 1000),
        (3, 75),
        (3, 150)
    ]
    i = 0
    for step in x.steps:
        if type(step) == FilterThrough:
            total_elutes = 0
            total_vol_added = 0
            for substep in step.base_steps:
                if type(substep) == CMove:
                    if (substep.from_vessel == 'flask_ether'
                            and substep.to_vessel == 'reactor'):
                        total_vol_added += substep.volume
                        total_elutes += 1
            assert total_elutes == tests[i][0]
            assert total_vol_added == tests[i][1]
            i += 1
    assert i == len(tests)

@pytest.mark.unit
def test_filter_eluting_with_more_than_to_vessel_max_volume():
    with pytest.raises(XDLError):
        xdl_f = os.path.join(
            FILES, 'filter_through_elute_more_than_to_vessel_max_volume.xdl')
        graph_f = os.path.join(GLOBAL_FILES, 'bigrig.json')
        x = XDL(xdl_f)
        x.prepare_for_execution(graph_f, interactive=False)

    with pytest.raises(XDLError):
        xdl_f = os.path.join(
            FILES, 'filter_through_elute_more_than_to_vessel_max_volume2.xdl')
        graph_f = os.path.join(GLOBAL_FILES, 'bigrig.json')
        x = XDL(xdl_f)
        x.prepare_for_execution(graph_f, interactive=False)
