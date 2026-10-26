import os
import pytest
from xdl import XDL
from xdl.steps import AbstractBaseStep, AbstractDynamicStep

HERE = os.path.abspath(os.path.dirname(__file__))

SNAPSHOT_FOLDER = os.path.join(HERE, 'snapshots')

@pytest.mark.skip(reason="Not an actual test")
def test_snapshot(name, new_snapshot: XDL):
    file_name = os.path.join(SNAPSHOT_FOLDER, f'{name}.xdlexe')

    # No existing snapshot, just save and return.
    if not os.path.exists(file_name):
        new_snapshot.executor.save_execution_script(file_name)
        return

    current_snapshot = XDL(file_name)
    compare_snapshots(current_snapshot, new_snapshot, name)

@pytest.mark.skip(reason="Not an actual test")
def compare_snapshots(current_snapshot: XDL, new_snapshot: XDL, name=None):
    assert len(current_snapshot.steps) == len(new_snapshot.steps)
    for i, step in enumerate(current_snapshot.steps):
        test_steps_identical(step, new_snapshot.steps[i], name)

@pytest.mark.skip(reason="Not an actual test")
def test_steps_identical(step1, step2, name=None):
    assert type(step1) == type(step2)
    for prop, val in step1.properties.items():
        if prop == 'children':
            for j, child in enumerate(step1.children):
                assert child.name == step2.children[j].name
                for child_prop, child_val in child.properties.items():
                    if child_val or step2.children[j].properties[child_prop]:
                        assert (
                            child_val
                            == step2.children[j].properties[child_prop]
                        )

        elif val or step2.properties[prop]:
            try:
                if type(val) == float:
                    assert f'{step2.properties[prop]:.4f}' == f'{val:.4f}'
                else:
                    assert step2.properties[prop] == val
            except AssertionError:
                raise AssertionError(
                    f'Property "{prop}": {val} (old) != {step2.properties[prop]} (new)\n\
 {name}'
                )
    if not isinstance(step1, (AbstractBaseStep, AbstractDynamicStep)):
        assert len(step1.steps) == len(step2.steps)
        for j, step in enumerate(step1.steps):
            test_steps_identical(step, step2.steps[j], name)
