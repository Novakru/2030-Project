import os
import pytest
from ...utils import generic_chempiler_test

HERE = os.path.abspath(os.path.dirname(__file__))
FILES = os.path.join(HERE, 'files')
GLOBAL_FILES = os.path.join(HERE, '..', 'files')

@pytest.mark.unit
def test_add_all_volumes():
    xdl_f = os.path.join(FILES, 'add_through.xdl')
    graph_f = os.path.join(FILES, 'bigrig_modified_add_through.json')
    generic_chempiler_test(xdl_f, graph_f)
