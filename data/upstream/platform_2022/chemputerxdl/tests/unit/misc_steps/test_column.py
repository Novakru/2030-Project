import os
import pytest
from ...utils import generic_chempiler_test

HERE = os.path.abspath(os.path.dirname(__file__))
FILES = os.path.join(HERE, 'files')
GLOBAL_FILES = os.path.join(HERE, '..', 'files')

@pytest.mark.unit
def test_column():
    """Test that RunColumn step works."""
    xdl_f = os.path.join(FILES, 'column.xdl')
    graph_f = os.path.join(GLOBAL_FILES, 'bigrig.json')
    generic_chempiler_test(xdl_f, graph_f)
