import os
import pytest
from ...utils import generic_chempiler_test

HERE = os.path.abspath(os.path.dirname(__file__))
FILES = os.path.join(HERE, 'files')
GLOBAL_FILES = os.path.join(HERE, '..', 'files')

@pytest.mark.unit
def test_wait_until():
    """Test WaitUntil step works correctly."""
    xdl_f = os.path.join(FILES, 'wait_until.xdl')
    graph_f = os.path.join(GLOBAL_FILES, 'bigrig.json')
    generic_chempiler_test(xdl_f, graph_f)
