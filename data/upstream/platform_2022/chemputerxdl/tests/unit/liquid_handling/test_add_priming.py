import pytest
import os
from xdl import XDL
from chemputerxdl.steps import Add, PrimePumpForAdd
from ...utils import generic_chempiler_test

HERE = os.path.abspath(os.path.dirname(__file__))
FILES = os.path.join(HERE, 'files')
GLOBAL_FILES = os.path.join(HERE, '..', 'files')

@pytest.mark.unit
def test_add_priming():
    xdl_f = os.path.join(FILES, 'add_priming_volume.xdl')
    graph_f = os.path.join(GLOBAL_FILES, 'bigrig.json')
    x = XDL(xdl_f)
    x.prepare_for_execution(graph_f, testing=True)
    for step in x.steps:
        if type(step) == Add:
            for substep in step.steps:
                if type(substep) == PrimePumpForAdd:
                    assert substep.volume == 0.5
    generic_chempiler_test(xdl_f, graph_f)
