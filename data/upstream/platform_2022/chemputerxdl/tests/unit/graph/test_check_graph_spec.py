import os
import pytest
from xdl import XDL
from xdl.utils.graph import get_graph
from chemputerxdl.graphgen.get_graph_spec import get_graph_spec
from chemputerxdl.graphgen.check_graph_spec import (
    check_template, check_graph_spec)
from chemputerxdl.graphgen.constants import (
    SWITCH_TO_OUT_EDGE,
    SWITCH_TO_IN_EDGE,
    REMOVE_DEST_PORT,
    REMOVE_SRC_PORT,
    NOT_ENOUGH_SPARE_PORTS,

    CANNOT_REACH_TARGET_TEMP_ERROR,
    INVALID_PORT_ERROR,
    MISSING_COMPONENT_TYPE_ERROR,
    MISSING_HEATER_OR_CHILLER_ERROR,
)

HERE = os.path.abspath(os.path.dirname(__file__))
FILES = os.path.join(HERE, 'files')

CHECK_TEMPLATE_TESTS = [
    ('check_graph_spec_bad_nitrogen_flask.json', {
        'fixable_issues': [SWITCH_TO_OUT_EDGE],
        'errors': [],
    }),
    ('check_graph_spec_bad_vacuum.json', {
        'fixable_issues': [SWITCH_TO_IN_EDGE],
        'errors': [],
    }),
    ('check_graph_spec_bad_valve_port.json', {
        'fixable_issues': [],
        'errors': [INVALID_PORT_ERROR]
    }),
    ('check_graph_spec_bad_reactor_port.json', {
        'fixable_issues': [],
        'errors': [INVALID_PORT_ERROR, INVALID_PORT_ERROR]
    }),
    ('check_graph_spec_unnecessary_ports.json', {
        'fixable_issues': [REMOVE_SRC_PORT, REMOVE_DEST_PORT],
        'errors': [],
    }),
]

CHECK_GRAPH_SPEC_TESTS = [
    ('check_graph_spec_not_enough_spare_ports.json', 'orgsyn_v83p0193.xdl', {
        'fixable_issues': [NOT_ENOUGH_SPARE_PORTS],
        'errors': []
    }),
    ('check_graph_spec_missing_component_type.json', 'orgsyn_v83p0193.xdl', {
        'fixable_issues': [],
        'errors': [MISSING_COMPONENT_TYPE_ERROR]
    }),
    ('check_graph_spec_missing_heater.json', 'orgsyn_v83p0193.xdl', {
        'fixable_issues': [],
        'errors': [MISSING_HEATER_OR_CHILLER_ERROR]
    }),
    (
        'check_graph_spec_cannot_reach_temp.json',
        'orgsyn_v83p0193_high_temp.xdl',
        {
            'fixable_issues': [],
            'errors': [CANNOT_REACH_TARGET_TEMP_ERROR]
        }
    ),
]

@pytest.mark.unit
def test_check_template():
    for test_graph_f, test_info in CHECK_TEMPLATE_TESTS:
        print(test_graph_f)
        graph = get_graph(os.path.join(FILES, test_graph_f))
        fixable_issues, errors = check_template(graph)
        assert len(errors) == len(test_info['errors'])
        assert len(fixable_issues) == len(test_info['fixable_issues'])
        issue_types = [issue['issue'] for issue in fixable_issues]
        for issue in test_info['fixable_issues']:
            assert issue in issue_types
        error_types = [error['error'] for error in errors]
        for error in test_info['errors']:
            assert error in error_types

@pytest.mark.unit
def test_check_graph_spec():
    for test_graph_f, test_xdl_f, test_info in CHECK_GRAPH_SPEC_TESTS:
        print(test_graph_f)
        graph = get_graph(os.path.join(FILES, test_graph_f))
        x = XDL(os.path.join(FILES, test_xdl_f))
        graph_spec = get_graph_spec(x)
        fixable_issues, errors = check_graph_spec(graph_spec, graph)
        assert len(errors) == len(test_info['errors'])
        assert len(fixable_issues) == len(test_info['fixable_issues'])
        issue_types = [issue['issue'] for issue in fixable_issues]
        for issue in test_info['fixable_issues']:
            assert issue in issue_types
        error_types = [error['error'] for error in errors]
        for error in test_info['errors']:
            assert error in error_types
