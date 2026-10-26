import os
import pytest
from xdl import XDL
from chemputerxdl.steps import Transfer
from chemputerxdl.executor.constants import (
    TRANSFER_ALL_VOLUME_FACTOR)

HERE = os.path.abspath(os.path.dirname(__file__))
FILES = os.path.join(HERE, 'files')
GLOBAL_FILES = os.path.join(HERE, '..', 'files')
BIGRIG = os.path.join(GLOBAL_FILES, 'bigrig.json')

@pytest.mark.unit
def test_add_all_volumes():
    x = XDL(os.path.join(FILES, 'add_all_volumes.xdl'))
    x.prepare_for_execution(BIGRIG, testing=True)
    volumes = [
        15 * TRANSFER_ALL_VOLUME_FACTOR,
        15 * TRANSFER_ALL_VOLUME_FACTOR,
        100
    ]
    i = 0
    for step in x.steps:
        if type(step) == Transfer:
            assert volumes[i] == step.estimated_volume
            i += 1

@pytest.mark.unit
def test_add_all_volumes_nested():
    """Test that all volumes are added to steps wrapped in Async or Repeat."""
    x = XDL(os.path.join(FILES, 'add_all_volumes_nested.xdl'))
    x.prepare_for_execution(BIGRIG, testing=True)
