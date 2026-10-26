import os
import pytest
from ...utils import generic_chempiler_test
from xdl import XDL
from chemputerxdl.steps import WashSolid, CMove
from chemputerxdl.constants import (
    DEFAULT_FILTER_EXCESS_REMOVE_FACTOR)

HERE = os.path.abspath(os.path.dirname(__file__))
FILES = os.path.join(HERE, 'files')
GLOBAL_FILES = os.path.join(HERE, '..', 'files')

@pytest.mark.unit
def test_wash_solid():
    """Test that WashSolid step works with temperature property."""
    xdl_f = os.path.join(FILES, 'wash_solid.xdl')
    graph_f = os.path.join(GLOBAL_FILES, 'bigrig.json')
    generic_chempiler_test(xdl_f, graph_f)

@pytest.mark.unit
def test_wash_solid_stirring():
    """Test that WashSolid step stir property works."""
    xdl_f = os.path.join(FILES, 'wash_solid.xdl')
    graph_f = os.path.join(GLOBAL_FILES, 'bigrig.json')
    x = XDL(xdl_f)
    x.prepare_for_execution(graph_f, testing=True)

    check_steps = x.steps[:-1]
    assert('StartStir' in [step.name for step in check_steps[-1].steps])

@pytest.mark.unit
def test_wash_solid_dead_volume():
    """Test that WashSolid takes dead volume into account when deciding volume
    to withdraw.
    """
    xdl_fs = [
        os.path.join(FILES, 'wash_solid.xdl'),
        os.path.join(GLOBAL_FILES, 'wash_in_rotavap.xdl'),
    ]
    graph_f = os.path.join(GLOBAL_FILES, 'bigrig.json')
    for xdl_f in xdl_fs:
        x = XDL(xdl_f)
        x.prepare_for_execution(graph_f, testing=True)

        check_steps = x.steps[:-1]
        for step in check_steps:
            if type(step) == WashSolid:
                if step.vessel_type == 'filter':
                    for substep in step.steps:
                        if type(step) == CMove:
                            assert step.filter_dead_volume == 10
                            assert (step.steps[-4].volume
                                    == 10 + (
                                        DEFAULT_FILTER_EXCESS_REMOVE_FACTOR
                                        * step.volume))
                else:
                    assert step.filter_dead_volume is None

# This test is only compatible with SL2. Reactivate after SL2 switch.
# @pytest.mark.unit
def test_vacuum_free_removal():
    """
    Test for checking that WashSolid step allows removal of liquid without
    attempting to apply a vacuum.
    """

    xdl_ugi = os.path.join(FILES, "ugi_procedure.xdl")
    graph_ugi = os.path.join(FILES, "ugi_graph_vacuum_free_wash_solid.json")

    x = XDL(xdl_ugi)
    x.prepare_for_execution(graph_ugi, testing=True)

    wash_solid = [step for step in x.steps if step.name == "WashSolid"][0]

    wash_solid_steps = ["StartStir", "Add", "Wait", "CMove", "StopStir"]
    assert [s.name for s in wash_solid.steps] == wash_solid_steps


@pytest.mark.unit
def test_wash_solid_no_vacuum():
    xdl_f = os.path.join(FILES, 'wash_solid_no_vacuum.xdl')
    graph_f = os.path.join(GLOBAL_FILES, 'bigrig.json')
    x = XDL(xdl_f)
    x.prepare_for_execution(graph_f, testing=True)
    for step in x.steps:
        if step.name == 'WashSolid':
            for substep in step.steps:
                assert substep.name != 'ApplyVacuum'
