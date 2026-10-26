"""Tests for testing locking as used in parallelization."""

import os
import pytest

from xdl import XDL
from chemputerxdl.constants import CHEMPUTER_WASTE
from chemputerxdl.utils.execution import get_chempiler

from ...utils import generic_chempiler_test

HERE = os.path.abspath(os.path.dirname(__file__))
FILES = os.path.join(HERE, 'files')
GLOBAL_FILES = os.path.join(HERE, '..', 'files')

xdl_f = os.path.join(FILES, 'xdllock.xdl')
graph_f = os.path.join(GLOBAL_FILES, 'bigrig.json')


@pytest.mark.unit
def test_generic_xdllocks():
    """Test that dissolving a solid in the rotavap works."""
    generic_chempiler_test(xdl_f, graph_f)


# unlock step
@pytest.mark.unit
def test_unlock_step():
    """Test Unlock step with both list and 'all'. """
    c = get_chempiler(graph=graph_f)
    xdl = XDL(xdl_f)
    xdl.prepare_for_execution(graph_f, interactive=False)

    pid = "__main"  # pid from xdl file

    nodes_to_unlock = ["buffer_flask", "filter"]
    nodes_remaining = ["rotavap"]

    for i in range(len(xdl.steps)):
        xdl.steps[i].acquire_locks(c, pid)
        xdl.steps[i].release_locks(c, pid)

    for node in nodes_to_unlock:
        assert c.graph[node]['xdl_locks']["ongoing"].pid is None

    for node in nodes_remaining:
        assert c.graph[node]['xdl_locks']["ongoing"].pid == pid
        # set back to None
        c.graph[node]['xdl_locks']["ongoing"].pid = None

    for i in range(len(xdl.steps)):
        xdl.steps[i].acquire_locks(c, "wrong_pid")
        xdl.steps[i].release_locks(c, "wrong_pid")

    for node in nodes_remaining:
        assert c.graph[node]['xdl_locks']["ongoing"].pid is not None


# unlock transfer
@pytest.mark.unit
def test_unlock_transfer():
    """Test that Transfer unlocks properly."""
    c = get_chempiler(graph=graph_f)
    xdl = XDL(xdl_f)
    xdl.prepare_for_execution(graph_f, interactive=False)

    # Check normal transfer step does not unlock
    # relevant step index from xdl procedure
    idx = 3

    assert xdl.steps[idx].name == "Transfer"
    assert xdl.steps[idx].unlock_after is False
    _, __, unlocks = xdl.steps[idx].steps[-1].locks(c)
    assert xdl.steps[idx].from_vessel not in unlocks

    # Check transfer step with unlock_after actually unlocks
    # relevant step index from xdl procedure
    idx = 8

    assert xdl.steps[idx].name == "Transfer"
    assert xdl.steps[idx].unlock_after is True
    _, __, unlocks = xdl.steps[idx].steps[-3].locks(c)
    assert xdl.steps[idx].from_vessel in unlocks
    assert xdl.steps[idx].to_vessel not in unlocks

# unlock clean vessel
@pytest.mark.unit
def test_unlock_cleanvessel():
    """Test that CleanVessel unlocks properly."""
    xdl = XDL(xdl_f)
    xdl.prepare_for_execution(graph_f, interactive=False)

    # relevant step index from xdl procedure
    idx = -3

    assert xdl.steps[idx].name == "CleanVessel"
    assert xdl.steps[idx].steps[-1].name == "Unlock"
    assert xdl.steps[idx].steps[-1].nodes[0] == xdl.steps[idx].vessel

# check wastes never locked
@pytest.mark.unit
def test_never_lock_wastes():
    """Test that Wastes never actually get locked."""
    c = get_chempiler(graph=graph_f)
    xdl = XDL(xdl_f)
    xdl.prepare_for_execution(graph_f, interactive=False)

    pid = "__main"

    for step in xdl.steps:
        _, ongoing, __ = step.locks(c)
        step.acquire_locks(c, pid)
        for node in ongoing:
            if c.graph[node]["class"] == CHEMPUTER_WASTE:
                # never lock wastes
                assert c.graph[node]['xdl_locks']["ongoing"].pid is None
            else:
                # check other locks were acquired as expected
                assert c.graph[node]['xdl_locks']["ongoing"].pid == pid
        step.release_locks(c, pid)

# overriden temp with ongoing lock
@pytest.mark.unit
def test_overwrite_temp_locks():
    """Test that Temp locks are overriden with Ongoing locks"""
    c = get_chempiler(graph=graph_f)
    xdl = XDL(xdl_f)
    xdl.prepare_for_execution(graph_f, interactive=False)

    pid = "__main"

    for step in xdl.steps:
        temp, ongoing, _ = step.locks(c)
        step.acquire_locks(c, pid)

        for node in ongoing:
            if node in temp:
                assert c.graph[node]['xdl_locks']["ongoing"].pid is pid
                assert c.graph[node]['xdl_locks']["temp"].pid is None

        step.release_locks(c, pid)
