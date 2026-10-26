import os
import pytest
from ...utils import remove_confirm_steps
from xdl import XDL

from xdl.steps import UnimplementedStep

HERE = os.path.abspath(os.path.dirname(__file__))
TESTOUTPUT = os.path.join(HERE, "test_output")
FILES = os.path.join(HERE, 'files')
os.makedirs(TESTOUTPUT, exist_ok=True)
GLOBAL_FILES = os.path.join(HERE, '..', 'files')

# Manual Test of adding 0 water


@pytest.mark.unit
def test_clean_backbone_integrated_in_add():
    """Add has a new optional bool to have an integrated step
    to clean the backbone."""
    xdl_f = os.path.join(FILES, 'add_nonzero_volume.xdl')
    graph_f = os.path.join(GLOBAL_FILES, 'bigrig.json')
    x = XDL(xdl_f)
    for i in reversed(range(len(x.steps))):
        if isinstance(x.steps[i], UnimplementedStep):
            x.steps.pop(i)
    x.prepare_for_execution(graph_f, testing=True)
    x.steps = [
        remove_confirm_steps(step) for step in x.steps]
    for xdlstep in x.steps:
        if xdlstep.name == 'Add':
            assert 'Wait' in [s.name for s in xdlstep.steps]
            assert 'CleanBackbone' in [s.name for s in xdlstep.steps]
