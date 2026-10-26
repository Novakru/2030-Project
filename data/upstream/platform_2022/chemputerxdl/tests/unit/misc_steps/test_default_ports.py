import os
import pytest
from xdl import XDL
from chemputerxdl.steps import Add, CMove, Dissolve, Transfer, Separate

HERE = os.path.abspath(os.path.dirname(__file__))
FILES = os.path.join(HERE, 'files')
GLOBAL_FILES = os.path.join(HERE, '..', 'files')

@pytest.mark.unit
def test_default_ports():
    """Test that dry step at specific pressure works in filter."""
    xdl_f = os.path.join(FILES, 'add_default_port.xdl')
    graph_f = os.path.join(GLOBAL_FILES, 'bigrig.json')
    x = XDL(xdl_f)
    x.prepare_for_execution(graph_f, testing=True)
    correct_ports = [
        'top',  # filter default
        '0',  # reactor default
        'evaporate',  # rotavap default
        'bottom',  # separator default
        'top',  # separator explicit

        'top',
        '0',
        'evaporate',

        ('0', 'bottom'),
        ('evaporate', 'top'),

        ('0', '0', 'bottom'),

    ]
    for step in x.steps:
        if type(step) in [Add, Dissolve]:
            correct_port = correct_ports.pop(0)
            for substep in step.steps:
                if type(substep) == CMove:
                    assert str(substep.to_port) == correct_port

        elif type(step) == Transfer:
            correct_from_port, correct_to_port = correct_ports.pop(0)
            for substep in step.steps:
                if type(substep) == CMove:
                    assert str(substep.from_port) == correct_from_port
                    assert str(substep.to_port) == correct_to_port

        elif type(step) == Separate:
            correct_from_port, correct_to_port, correct_waste_phase_to_port =\
                correct_ports.pop(0)
            assert str(step.from_port) == correct_from_port
            assert str(step.to_port) == correct_to_port
            assert str(step.waste_phase_to_port) == correct_waste_phase_to_port
