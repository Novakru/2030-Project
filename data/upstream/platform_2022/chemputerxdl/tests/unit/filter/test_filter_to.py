import pytest
import os
from xdl.errors import XDLError

from ...utils import generic_chempiler_test

HERE = os.path.abspath(os.path.dirname(__file__))
FILES = os.path.join(HERE, 'files')
GLOBAL_FILES = os.path.join(HERE, '..', 'files')

@pytest.mark.unit
def test_filter_to():
    xdl_f = os.path.join(FILES, 'filter_to.xdl')
    graph_f = os.path.join(GLOBAL_FILES, 'bigrig.json')
    generic_chempiler_test(xdl_f, graph_f)
    with pytest.raises(XDLError):
        xdl_f = os.path.join(FILES, 'filter_to_error.xdl')
        graph_f = os.path.join(FILES, 'filter_to_error_graph.json')
        generic_chempiler_test(xdl_f, graph_f)
