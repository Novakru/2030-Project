import pytest
import os
from ...utils import generic_chempiler_test

HERE = os.path.abspath(os.path.dirname(__file__))
FILES = os.path.join(HERE, 'files')

@pytest.mark.unit
def test_one_valve_backbone():
    xdl_f = os.path.join(FILES, 'one-valve-test.xdl')
    graph_f = os.path.join(FILES, 'one-valve-graph.json')
    generic_chempiler_test(xdl_f, graph_f)
