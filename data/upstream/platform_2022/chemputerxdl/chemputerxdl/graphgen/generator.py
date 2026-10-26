"""
.. module:: graphgen.generator
    :platforms: Unix, Windows
    :synopsis: Generates a graph object from a graph file

"""
# Std
from typing import Dict, List
import json
import os

# Other
from networkx.readwrite import node_link_data

# XDL
from xdl.errors import XDLError
from xdl.utils.logging import get_logger
from xdl.utils.graph import get_graph

# Relative
from .constants import (
    REMOVE_SRC_PORT,
    REMOVE_DEST_PORT,
    SRC_PORT_INVALID,
    DEST_PORT_INVALID,
    SWITCH_TO_IN_EDGE,
    SWITCH_TO_OUT_EDGE,
    ADD_CHILLER_TO_REACTOR,
    NOT_ENOUGH_SPARE_PORTS
)
from .issue_fixers import (
    fix_issue_remove_src_port,
    fix_issue_remove_dest_port,
    fix_issue_src_port_invalid,
    fix_issue_dest_port_invalid,
    fix_issue_switch_to_in_edge,
    fix_issue_switch_to_out_edge,
    fix_issue_add_chiller_to_reactor,
    fix_issue_not_enough_spare_ports
)
from .check_graph_spec import check_graph_spec
from .get_graph_spec import get_graph_spec
from .apply_graph_spec import apply_spec_to_template


# Path to template graph file
HERE = os.path.abspath(os.path.dirname(__file__))
DEFAULT_TEMPLATE = os.path.join(HERE, 'template.json')

# Issues that can be addressed
FIXABLE_ISSUES = {
    REMOVE_SRC_PORT: fix_issue_remove_src_port,
    REMOVE_DEST_PORT: fix_issue_remove_dest_port,
    SRC_PORT_INVALID: fix_issue_src_port_invalid,
    DEST_PORT_INVALID: fix_issue_dest_port_invalid,
    SWITCH_TO_IN_EDGE: fix_issue_switch_to_in_edge,
    SWITCH_TO_OUT_EDGE: fix_issue_switch_to_out_edge,
    ADD_CHILLER_TO_REACTOR: fix_issue_add_chiller_to_reactor,
    NOT_ENOUGH_SPARE_PORTS: fix_issue_not_enough_spare_ports
}

def graph_from_template(
    xdl_obj,
    template: str = None,
    save: str = None,
    auto_fix_issues: bool = False,
    ignore_errors: List = []
) -> Dict:
    """Generates a NetworkX graph object from a given template file.

    Args:
        xdl_obj (XDL): [description]
        template (str, optional): Path to template file. Defaults to None.
        save (str, optional): Where to save the new template. Defaults to None.
        auto_fix_issues (bool, optional): Fix issues automatically.
                                            Defaults to False.
        ignore_errors (List, optional): List of errors to ignore.
                                        Defaults to [].

    Raises:
        XDLError: Errors raised in graph creation/generation

    Returns:
        Dict: Newly created graph
    """

    # Get the logger
    logger = get_logger()

    # Create a graph object from given template
    if template is None:
        template = DEFAULT_TEMPLATE
    graph = get_graph(template)

    # Get the specification of the graph
    graph_spec = get_graph_spec(xdl_obj, graph)

    # Find any fixable isses and errors
    fixable_issues, errors = check_graph_spec(graph_spec, graph)

    # Find errors that aren't meant  o be ignored
    errors = [error for error in errors if error['error'] not in ignore_errors]

    # Raise any unrecoverable errors
    if errors:
        error_str = '\n  -- '.join([error['msg'] for error in errors])
        error_str = '  -- ' + error_str
        raise XDLError(f'Graph template supplied cannot be used for this\
 procedure. Errors:\n{error_str}')

    # Attempt to fix any issues that can be fixed
    if fixable_issues:
        # Not automatically fixing them
        if not auto_fix_issues:
            # Iterate through all issues
            for issue in fixable_issues:
                # Check the issue can actually be fixed
                assert issue['issue'] in FIXABLE_ISSUES

                # Promt user to fix the issue automatically
                question = f'{issue["msg"]}. Fix automatically? [Y/n]'
                answer = input(question)
                while answer not in ['y', 'Y', 'n', 'N', '']:
                    answer = input(question)
                if not answer or answer in ['y', 'Y']:
                    continue

                # Raise error if unfixed
                elif answer in ['n', 'N']:
                    raise XDLError(f'Graph template supplied cannot be used for\
 this procedure. Issue: {issue["msg"]}')

        # Fix the issue
        for issue in fixable_issues:
            logger.info(f'Fixing issue: {issue["msg"]}')
            FIXABLE_ISSUES[issue['issue']](graph, issue)

    # Apply the new graph spec to the template
    apply_spec_to_template(xdl_obj, graph_spec, graph, fixable_issues)

    # Save to disk
    if save:
        # Convert ports to strings
        for _, _, data in graph.edges(data=True):
            src_port, dest_port = data['port']
            data['port'] = f'({src_port},{dest_port})'
        data = node_link_data(graph)
        with open(save, 'w') as fd:
            json.dump(data, fd, indent=2)

    # Return loaded graph object
    return graph
