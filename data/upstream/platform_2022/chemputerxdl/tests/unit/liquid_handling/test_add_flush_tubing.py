import pytest
import os
from xdl import XDL

HERE = os.path.abspath(os.path.dirname(__file__))
FILES = os.path.join(HERE, 'files')
GLOBAL_FILES = os.path.join(HERE, '..', 'files')

@pytest.mark.unit
def test_add_flush_tubing():
    x = XDL(os.path.join(FILES, 'repeat_parent.xdl'))
    x.prepare_for_execution(
        os.path.join(GLOBAL_FILES, 'bigrig.json'), testing=True)
    for step in x.steps:
        if step.name == 'Repeat':
            for child in step.children:
                if child.name == 'Add':
                    flush_tube_steps = [
                        substep for substep in child.steps
                        if substep.name == 'FlushTubing'
                    ]
                    assert len(flush_tube_steps) == 1
                    assert (
                        flush_tube_steps[0].flush_tube_vessel
                        == 'flask_nitrogen'
                    )

@pytest.mark.unit
def test_add_flush_tubing_no_backbone_inert_gas():
    x = XDL(os.path.join(FILES, 'repeat_parent.xdl'))
    x.prepare_for_execution(
        os.path.join(FILES, 'bigrig_no_backbone_inert_gas.json'),
        testing=True,

        # Avoid diff as repeat_parent.xdlexe is not in .gitignore.
        save_path=os.path.join(FILES, 'repeat_parent_no_inert_gas.xdlexe')
    )
    for step in x.steps:
        if step.name == 'Repeat':
            for child in step.children:
                if child.name == 'Add':
                    flush_tube_steps = [
                        substep for substep in child.steps
                        if substep.name == 'FlushTubing'
                    ]
                    assert len(flush_tube_steps) == 1
                    assert len(flush_tube_steps[0].steps) == 0
