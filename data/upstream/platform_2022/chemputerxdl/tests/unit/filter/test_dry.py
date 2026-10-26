import os
import pytest
from ...utils import generic_chempiler_test
from xdl import XDL

HERE = os.path.abspath(os.path.dirname(__file__))
FILES = os.path.join(HERE, 'files')
GLOBAL_FILES = os.path.join(HERE, '..', 'files')

@pytest.mark.unit
def test_dry_in_filter():
    """Test that dry step at specific pressure works in filter."""
    xdl_f = os.path.join(FILES, 'dry_in_filter.xdl')
    graph_f = os.path.join(GLOBAL_FILES, 'bigrig.json')
    generic_chempiler_test(xdl_f, graph_f)

@pytest.mark.unit
def test_dry_in_reactor():
    """Test that dry step at specific pressure works in reactor."""
    xdl_f = os.path.join(FILES, 'dry_in_reactor.xdl')
    graph_f = os.path.join(GLOBAL_FILES, 'bigrig.json')
    generic_chempiler_test(xdl_f, graph_f)

@pytest.mark.unit
def test_dry_in_rotavap():
    """Test that dry step at specific pressure works in reactor."""
    xdl_f = os.path.join(FILES, 'dry_in_rotavap.xdl')
    graph_f = os.path.join(GLOBAL_FILES, 'bigrig.json')
    generic_chempiler_test(xdl_f, graph_f)

@pytest.mark.unit
def test_ullmann_dry_in_rotavap():
    """Test step causing trouble works properly."""
    xdl_f = os.path.join(FILES, 'Ullmann_dry.xdl')
    graph_f = os.path.join(FILES, 'Ullmann_dry_graph.json')
    x = XDL(xdl_f)
    x.prepare_for_execution(graph_f, testing=True)
    for step in x.steps:
        if step.name == 'Dry':
            for substep in step.steps:
                if substep.name == 'ApplyVacuum':
                    vacuum_steps = substep.steps
                    start_vacuum = [
                        vacuum_step
                        for vacuum_step in vacuum_steps
                        if vacuum_step.name == 'StartVacuum'
                    ]
                    assert len(start_vacuum) == 1
                    assert start_vacuum[0].vessel == step.vessel

    generic_chempiler_test(xdl_f, graph_f)

@pytest.mark.unit
def test_dry_inert_gas_connection():
    """Test confirms issue #112 fixed during reworking of Dry."""
    from xdl import XDL
    from chemputerxdl.steps.steps_base.general import CConnect

    xdl_f = os.path.join(FILES, 'dry.xdl')
    graph_f = os.path.join(FILES, 'bigrig_no_vacuum_device.json')
    generic_chempiler_test(xdl_f, graph_f)

    x = XDL(xdl_f)
    x.prepare_for_execution(
        graph_f,
        testing=True,
    )
    for step in x.steps:
        if step.name == 'Dry':
            for substep in step.steps:
                if type(substep) == CConnect:
                    assert substep.from_vessel == 'flask_nitrogen'
