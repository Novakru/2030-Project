"""
.. module:: graphgen.issue_fixers
    :platform: Unix, Windows
    :synopsis: Fixes common issues in the graph generation

"""

import copy
from typing import Dict
from networkx import MultiDiGraph

# XDL
from xdl.errors import XDLError
from xdl.utils.graph import undirected_neighbors

# Relative
from .utils import (
    get_new_node_id, get_new_edge_id
)
from .constants import GRIDSIZE, DEFAULT_CHILLER_DATA
from .utils import extend_backbone
from ..constants import VALID_PORTS, CHILLER_CLASSES

def fix_issue_src_port_invalid(graph: MultiDiGraph, issue: Dict):
    """Fixes the issue when a supplied source port is invalid.

    Args:
        graph (MultiDiGraph): Graph to check/fix
        issue (Dict): Issue information
    """

    # Iterate through source edges in the graph
    for src, _, data in graph.edges(data=True):
        # Get the port information
        src_port, dest_port = data['port']

        # Issue src/dest prot are the same as edge src/dest port
        if issue['src_port'] == src_port and issue['dest_port'] == dest_port:
            # Get class of the src node
            src_class = graph.nodes[src]['class']

            # Check its present in valid ports and only has one port
            assert src_class in VALID_PORTS
            assert len(VALID_PORTS[src_class]) == 1

            # Change the port if needed to correct src port
            data['port'] = [VALID_PORTS[src_class][0], dest_port]

            return

def fix_issue_dest_port_invalid(graph: MultiDiGraph, issue: Dict):
    """Fixes the issue when a supplied destination port is invalid

    Args:
        graph (MultiDiGraph): Graph to check/fix
        issue (Dict): Issue information
    """

    # Iterate through all dest edges in the graph
    for _, dest, data in graph.edges(data=True):
        # Get port information
        src_port, dest_port = data['port']

        # Issue src/dest port match the current src/dest port
        if issue['src_port'] == src_port and issue['dest_port'] == dest_port:
            # Get destination node class
            dest_class = graph.nodes[dest]['class']

            # Check that it's present in valid ports and only has one port
            assert dest_class in VALID_PORTS
            assert len(VALID_PORTS[dest_class]) == 1

            # Change the port if needed to correct dest port
            data['port'] = [src_port, VALID_PORTS[dest_class][0]]

            return

def fix_issue_replace_flask_with_cartridge(graph: MultiDiGraph, issue: Dict):
    """Replaces a flask with a cartridge

    Args:
        graph (MultiDiGraph): Graph to check/fix
        issue (Dict): Issue information

    Raises:
        XDLError: No flask found to replace with cartridge
    """

    # Iterate through all neighboring nodes of the issue valve
    for neighbor in undirected_neighbors(graph, issue['valve']):
        # Flask is present so remove from the graph
        if graph.nodes[neighbor]['class'] == 'ChemputerFlask':
            graph.remove_node(neighbor)
            return

    # Raise error if flask not found
    raise XDLError(f'No flask found connected to {issue["valve"]} for removal\
 to make way for cartridge.')

def reverse_edge(graph: MultiDiGraph, issue: Dict):
    """Reverses an edge on the graph

    Args:
        graph (MultiDiGraph): Grpah to check/fix
        issue (Dict): Issue information
    """

    # Define the edge to reverse
    edge_to_reverse = None

    # Iterate through all edges on the graph
    for src, dest, data in graph.edges(data=True):
        # Found the issue edge
        if src == issue['src'] and dest == issue['dest']:
            # Get port information
            src_port, dest_port = data['port']

            # Set edge_to_reverse and break out of iteration
            edge_to_reverse = (src, dest, data)
            break

    # Check we have an edge to reverse
    assert edge_to_reverse

    # Reverse the data
    reversed_data = edge_to_reverse[2]
    reversed_data['port'] = [dest_port, src_port]

    # Remove old edge
    graph.remove_edge(src, dest)

    # Add newly reversed edge
    graph.add_edge(dest, src, **reversed_data)

def fix_issue_switch_to_in_edge(graph: MultiDiGraph, issue: Dict):
    """Switch an out edge to an in edge

    Args:
        graph (MultiDiGraph): Graph to check/fix
        issue (Dict): Issue information
    """

    # Reverse the edge
    reverse_edge(graph, issue)

def fix_issue_switch_to_out_edge(graph: MultiDiGraph, issue: Dict):
    """Switch an in edge to an out edge

    Args:
        graph (MultiDiGraph): Graph to check/fix
        issue (Dict): Issue Information
    """

    # Reverse the edge
    reverse_edge(graph, issue)

def fix_issue_remove_src_port(graph: MultiDiGraph, issue: Dict):
    """Remove a source port from an edge

    Args:
        graph (MultiDiGraph): Graph to check/fix
        issue (Dict): Issue information
    """

    # Iterate through all graph edges
    for src, dest, data in graph.edges(data=True):
        # Found Issue edge to fix
        if src == issue['src'] and dest == issue['dest']:

            # Get port information
            _, dest_port = data['port']

            # Remove the src port
            data['port'] = ['', dest_port]

def fix_issue_remove_dest_port(graph: MultiDiGraph, issue: Dict):
    """Remove destination port from graph edge

    Args:
        graph (MultiDiGraph): Graph to check/fix
        issue (Dict): Issue information
    """

    # iterate through all edges of the graph
    for src, dest, data in graph.edges(data=True):
        # Found issue edge
        if src == issue['src'] and dest == issue['dest']:
            # Get port information
            src_port, _ = data['port']

            # Remove destination port
            data['port'] = [src_port, '']

def fix_issue_add_chiller_to_reactor(graph, issue):
    """Fix issue where reactor requires a chiller but only has a hotplate
    stirrer. If chiller already present in graph, connect and edge from it to
    the reactor. Otherwise make a new chiller node and connect it to the
    reactor.
    """
    reactor = graph.nodes[issue['reactor']]
    for node, data in graph.nodes(data=True):
        if data['class'] in CHILLER_CLASSES:
            chiller = node
            chiller_data = data
            break
    else:
        chiller = 'chiller'
        chiller_data = copy.deepcopy(DEFAULT_CHILLER_DATA)
        chiller_data['internalId'] = get_new_node_id(graph)
        chiller_data['y'] = reactor['y'] + GRIDSIZE * 2
        chiller_data['x'] = reactor['x'] + GRIDSIZE * 2
        graph.add_node(chiller, **chiller_data)

    edge_data = {
        'id': get_new_edge_id(graph),
        'source': chiller,
        'target': issue['reactor'],
        'sourceInternal': chiller_data['internalId'],
        'targetInternal': reactor['internalId'],
        'port': ['', '']
    }

    graph.add_edge(
        chiller,
        issue['reactor'],
        **edge_data
    )

def fix_issue_not_enough_spare_ports(graph, issue):
    extra_ports_added = 4
    extra_valves = 1
    while extra_ports_added < issue['extra_ports']:
        extra_valves += 1
        extra_ports_added += 3
    extend_backbone(graph, extra_valves)
