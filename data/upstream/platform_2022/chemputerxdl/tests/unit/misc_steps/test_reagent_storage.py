import os
import pytest
from xdl import XDL
from chemputerxdl.steps import (
    StartStir, StopStir, StartHeatChill, StopHeatChill)
from chemputerxdl.constants import DEFAULT_STIR_REAGENT_FLASK_SPEED

HERE = os.path.abspath(os.path.dirname(__file__))
FILES = os.path.join(HERE, 'files')
GLOBAL_FILES = os.path.join(HERE, '..', 'files')

@pytest.mark.unit
def test_stirred_reagents():
    """Test reagent flasks needing stirring work."""
    xdl_f = os.path.join(FILES, 'stirred_reagents.xdl')
    graph_f = os.path.join(GLOBAL_FILES, 'bigrig.json')
    x = XDL(xdl_f)
    x.prepare_for_execution(graph_f, testing=True)

    check_steps = x.steps[:-1]
    for step in x.steps:
        print(step.name, step.properties, '\n')
    assert type(check_steps[0]) == StartStir
    assert check_steps[0].vessel == 'flask_water'
    assert check_steps[0].stir_speed == DEFAULT_STIR_REAGENT_FLASK_SPEED
    assert type(check_steps[1]) == StopStir

@pytest.mark.unit
def test_temp_controlled_reagents():
    """Test reagent flasks needing stirring work."""
    xdl_f = os.path.join(FILES, 'temp_controlled_reagents.xdl')
    graph_f = os.path.join(GLOBAL_FILES, 'bigrig.json')
    x = XDL(xdl_f)
    x.prepare_for_execution(graph_f, testing=True)

    check_steps = x.steps[:-1]
    assert type(check_steps[0]) == StartHeatChill
    assert check_steps[0].vessel == 'flask_water'
    assert check_steps[0].temp == 5
    assert type(check_steps[-1]) == StopHeatChill
