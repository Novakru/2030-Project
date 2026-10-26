from chemputerxdl.executor import ChemputerExecutor
from chemputerxdl.executor.errors import XDLInvalidPortError
from chemputerxdl.steps import Add, Transfer
import pytest
import os

HERE = os.path.abspath(os.path.dirname(__file__))
FILES = os.path.join(HERE, 'files')
GLOBAL_FILES = os.path.join(HERE, '..', 'files')

@pytest.mark.unit
def test_port_validation():
    executor = ChemputerExecutor()
    bigrig = os.path.join(GLOBAL_FILES, 'bigrig.json')
    with pytest.raises(XDLInvalidPortError):
        block = [Add(reagent="water", vessel="reactor", volume=5, port="top")]
        executor.prepare_block_for_execution(bigrig, block)

    block = [Add(reagent="water", vessel="reactor", volume=5, port="1")]
    executor.prepare_block_for_execution(bigrig, block)

    block = [Add(reagent="water", vessel="reactor", volume=5, port="0")]
    executor.prepare_block_for_execution(bigrig, block)

    with pytest.raises(XDLInvalidPortError):
        block = [Transfer(
            from_vessel="rotavap",
            to_vessel="reactor",
            volume=5,
            from_port="top")]
        executor.prepare_block_for_execution(bigrig, block)

    block = [Transfer(
        from_vessel="rotavap",
        to_vessel="reactor",
        volume=5,
        from_port="evaporate")]
    executor.prepare_block_for_execution(bigrig, block)
    block = [Transfer(
        from_vessel="rotavap",
        to_vessel="reactor",
        volume=5,
        from_port="collect")]
    executor.prepare_block_for_execution(bigrig, block)

    with pytest.raises(XDLInvalidPortError):
        block = [Transfer(
            from_vessel="rotavap",
            to_vessel="filter",
            volume=5,
            to_port="0")]
        executor.prepare_block_for_execution(bigrig, block)

    block = [Transfer(
        from_vessel="rotavap",
        to_vessel="filter",
        volume=5,
        to_port="top")]
    executor.prepare_block_for_execution(bigrig, block)
    block = [Transfer(
        from_vessel="rotavap",
        to_vessel="filter",
        volume=5,
        to_port="bottom")]
    executor.prepare_block_for_execution(bigrig, block)
