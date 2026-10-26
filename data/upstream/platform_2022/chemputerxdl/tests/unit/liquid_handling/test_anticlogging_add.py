import os
import pytest
from xdl import XDL
from chemputerxdl.steps import Add, CMove, Wait
from ...utils import generic_chempiler_test

HERE = os.path.abspath(os.path.dirname(__file__))
FILES = os.path.join(HERE, 'files')
GLOBAL_FILES = os.path.join(HERE, '..', 'files')

test_info = [
    {
        'solvent_volume': int(
            Add.DEFAULT_PROPS['anticlogging_solvent_volume'].rstrip(' mL')
        ),
        'reagent_volume': int(
            Add.DEFAULT_PROPS['anticlogging_reagent_volume'].rstrip(' mL')
        ),
        'n_adds': 7,
    },
    {
        'solvent_volume': 3,
        'reagent_volume': 20,
        'n_adds': 4,
    }
]

@pytest.mark.unit
def test_anticlogging_add():
    """Test that dry step at specific pressure works in filter."""
    xdl_f = os.path.join(FILES, 'anticlogging_add.xdl')
    graph_f = os.path.join(GLOBAL_FILES, 'bigrig.json')
    x = XDL(xdl_f)
    x.prepare_for_execution(graph_f, testing=True)

    add_step_i = 0

    for step in x.steps:
        if type(step) == Add:
            correct_info = test_info[add_step_i]
            assert (step.anticlogging_solvent_volume
                    == correct_info['solvent_volume'])
            assert (step.anticlogging_reagent_volume
                    == correct_info['reagent_volume'])

            # Test correct number of add cycles are being done
            move_count = 0
            i = 0
            while i < len(step.steps) and type(step.steps[i]) != Wait:
                if type(step.steps[i]) == CMove:
                    move_count += 0.5
                i += 1
            assert move_count == correct_info['n_adds']

            add_step_i += 1

    generic_chempiler_test(xdl_f, graph_f)
