import os
import pytest

from xdl import XDL
from ...utils import generic_chempiler_test

HERE = os.path.dirname(os.path.abspath(__file__))
FILES = os.path.join(HERE, "files")

@pytest.mark.unit
def test_solid_dispenser_present():
    xdl_f = os.path.join(FILES, "solidhandler.xdl")
    graph_f = os.path.join(FILES, "solidhandler.json")

    x = XDL(xdl_f)
    x.prepare_for_execution(graph_f, testing=True)

    ds = x.steps[0]  # Dispenser step
    sub_ds = ds.steps[0]  # Substep of Dispenser step

    assert(ds.properties["dispenser"] is not None)
    assert(ds.properties["dispenser"] == "solid_wheel")
    assert(
        sub_ds.properties["device_name"] == ds.properties["dispenser"]
    )

@pytest.mark.unit
def test_solid_dispenser():
    xdl_f = os.path.join(FILES, "solidhandler.xdl")
    graph_f = os.path.join(FILES, "solidhandler.json")
    generic_chempiler_test(xdl_f, graph_f)
