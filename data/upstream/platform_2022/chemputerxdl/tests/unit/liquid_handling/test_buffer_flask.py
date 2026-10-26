import os
import pytest
from ...utils import generic_chempiler_test

HERE = os.path.abspath(os.path.dirname(__file__))
FILES = os.path.join(HERE, 'files')
GLOBAL_FILES = os.path.join(HERE, '..', 'files')

@pytest.mark.unit
def test_buffer_flask():
    """Test that buffer flask works."""
    xdl_f = os.path.join(GLOBAL_FILES, 'buffer_flask.xdl')
    graph_f = os.path.join(FILES, 'AF-4-Tr-RBF.graphml')
    generic_chempiler_test(xdl_f, graph_f)
