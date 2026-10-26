import os
# import pytest
from ...utils import generic_chempiler_test
from xdl import XDL

HERE = os.path.abspath(os.path.dirname(__file__))
FILES = os.path.join(HERE, 'files')

def test_custom_test():
    """A test for hardware mapping (multiple-reactors)
    retained to test future implementations"""
    xdl_f = os.path.join(FILES, 'multi_reactor.xdl')
    graph_f = os.path.join(FILES, 'graph_3reactor.json')

    x = XDL(xdl_f)
    x.prepare_for_execution(graph_f, testing=True)

    for xdl_harware_id, graph_hardware_id in x.hardware_map.items():
        assert xdl_harware_id == xdl_harware_id

    generic_chempiler_test(xdl_f, graph_f)
