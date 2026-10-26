import os
import pytest
from ...utils import generic_chempiler_test
from xdl import XDL
from chemputerxdl.steps import Filter, StopStir, StartStir

HERE = os.path.abspath(os.path.dirname(__file__))
FILES = os.path.join(HERE, 'files')
GLOBAL_FILES = os.path.join(HERE, '..', 'files')

@pytest.mark.unit
def test_filter_with_stirring():
    """Test that Filter step works with stirring."""
    xdl_f = os.path.join(FILES, 'filter_with_stirring.xdl')
    graph_f = os.path.join(GLOBAL_FILES, 'bigrig.json')
    x = XDL(xdl_f)
    x.prepare_for_execution(graph_f, testing=True)
    for step in x.steps:
        if type(step) == Filter:
            assert type(step.steps[0]) == StartStir
            assert type(step.steps[2]) == StopStir
    generic_chempiler_test(xdl_f, graph_f)

@pytest.mark.unit
def test_filter_without_stirring():
    """Test that Filter step stir works without stirring."""
    xdl_f = os.path.join(FILES, 'filter_without_stirring.xdl')
    graph_f = os.path.join(GLOBAL_FILES, 'bigrig.json')
    x = XDL(xdl_f)
    x.prepare_for_execution(graph_f, testing=True)
    for step in x.steps:
        if type(step) == Filter:
            assert type(step.steps[0]) == StopStir
    generic_chempiler_test(xdl_f, graph_f)

@pytest.mark.unit
def test_filter_inline():
    """Test that Filter step stir works with inline filter."""
    xdl_f = os.path.join(FILES, 'filter_inline.xdl')
    graph_f = os.path.join(GLOBAL_FILES, 'bigrig.json')
    x = XDL(xdl_f)
    x.prepare_for_execution(graph_f, testing=True)
    generic_chempiler_test(xdl_f, graph_f)

@pytest.mark.unit
def test_filter_use_filtrate():
    """Test that no vacuum applied when using filtrate."""
    xdl_f = os.path.join(FILES, 'filter_inline.xdl')
    graph_f = os.path.join(GLOBAL_FILES, 'bigrig.json')
    x = XDL(xdl_f)
    x.prepare_for_execution(graph_f, testing=True)
    for step in x.steps:
        if step.name == 'Filter':
            assert (
                not any([step.name == 'ApplyVacuum' for step in x.steps])
                and step.vacuum_attached
            )
