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
def test_add_0_from_flask_water_to_reactor():
    """Test that dissolving a solid in the rotavap works."""
    xdl_f = os.path.join(FILES, 'add_zero_volume.xdl')
    graph_f = os.path.join(GLOBAL_FILES, 'bigrig.json')
    x = XDL(xdl_f)
    for i in reversed(range(len(x.steps))):
        if isinstance(x.steps[i], UnimplementedStep):
            x.steps.pop(i)
    x.prepare_for_execution(graph_f, testing=True)
    x.steps = [
        remove_confirm_steps(step) for step in x.steps]
    add_steps = x.steps[0]                 # The add step is the first one
    assert len(add_steps.steps) == 0       # It should have 0 instead of 5 steps
