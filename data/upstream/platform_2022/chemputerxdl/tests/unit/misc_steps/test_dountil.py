import os
import pytest

from ...utils import generic_chempiler_test

HERE = os.path.abspath(os.path.dirname(__file__))
FILES = os.path.join(HERE, 'files')

PROCEDURE_FILE = 'dountil.xdl'
PROCEDURE_GRAPH = 'dountil.json'


@pytest.mark.unit
def test_dountil():
    """ Test DoUntil wrapper step.

    Simulation works properly, so just checking if it works.
    """

    xdl_f = os.path.join(FILES, PROCEDURE_FILE)
    graph_f = os.path.join(FILES, PROCEDURE_GRAPH)
    generic_chempiler_test(xdl_f, graph_f)
