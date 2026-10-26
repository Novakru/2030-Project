"""
..module:: executor.graph
    :platforms: Windows, Unix
    :synopsis: Obtains relevant information such as vessels and ports from the
                Chemputer graph.

"""

from typing import Dict
import hashlib
import json

from networkx import MultiDiGraph, NetworkXNoPath, MultiGraph
from networkx.algorithms.shortest_paths.generic import shortest_path_length

from xdl.hardware.components import Component, Hardware
from ..constants import VACUUM_CLASSES

def hardware_from_graph(graph: MultiDiGraph) -> Hardware:
    """Given networkx graph return a Hardware object corresponding to
    setup described in the graph.

    Args:
        graph (networkx.MultiDiGraph): networx graph of setup.

    Returns:
        Hardware: Hardware object containing graph described in input given.
    """

    # List to hold the hardware components
    components = []

    # Iterate through each node in the graph
    for node in graph.nodes():
        # Get the node's properties
        props = graph.nodes[node]

        # Set type to the class property and create hardware component
        props['type'] = props['class']
        component = Component(node, props['type'])

        # Default flasks with no chemical assigned to empty
        if props['type'] == 'ChemputerFlask' and 'chemical' not in props:
            props['chemical'] = ''

        # Update the hardware component properties
        component.properties.update(props)

        # Add to list
        components.append(component)

    # Hardware present in the Chemputer graph
    return Hardware(components)

def make_vessel_map(
    graph: MultiDiGraph, target_vessel_class: str
) -> Dict[str, str]:
    """Given graph, make dict with nodes as keys and nearest waste vessels to
    each node as values, i.e. {node: nearest_waste_vessel}.

    Args:
        graph (networkx.MultiDiGraph): networkx graph of setup.

    Returns:
        Dict[str, str]: dict with nodes as keys and nearest waste vessels as
                        values.
    """

    # Make graph undirected so actual closest waste vessels are found, not
    # closest in liquid flow path. As long as vessels are all attached to a
    # valve which is attached to a waste vessel this should be fine.
    vessel_map = {}
    undirected_graph = MultiGraph(graph)

    # Obtain all target vessels from Undirected graph
    target_vessels = [
        node for node in undirected_graph.nodes()
        if (undirected_graph.nodes[node]['type']
            == target_vessel_class)
    ]

    # Iterate through each graph node
    for node in undirected_graph.nodes():
        # Get node information
        node_info = undirected_graph.nodes[node]

        # Node is not of target vessel class type
        if node_info['type'] != target_vessel_class:
            # Distance and closest vessel
            shortest_path_found = 100000
            closest_target_vessel = None

            # Iterate through each target vessel
            for target_vessel in target_vessels:
                # Attept to find shortest path to the target vesesl
                try:
                    shortest_path_to_target_vessel = shortest_path_length(
                        undirected_graph, source=node, target=target_vessel
                    )

                    # Set new distance and vessel if shorter than previous
                    if shortest_path_to_target_vessel < shortest_path_found:
                        shortest_path_found = shortest_path_to_target_vessel
                        closest_target_vessel = target_vessel

                # No Path found in the graph, just ignore and move on
                except NetworkXNoPath:
                    pass

            # Update vessel map
            vessel_map[node] = closest_target_vessel

    return vessel_map

def get_unused_valve_port(valve_node: str, graph: MultiDiGraph) -> int:
    """Given a valve, return a position where the valve isn't connected to
    anything.

    Args:
        valve_node (str): Name of the valve on which to find an unused port.
        graph (MultiDiGraph): Graph that contains valve.

    Returns:
        int: Valve position which is not connected to anything. If there is no
            unconnected position then None is returned.
    """
    # List for logging used ports
    used_ports = []

    # Get connected valve positions.
    for _, _, edge_data in graph.in_edges(valve_node, data=True):
        if 'port' in edge_data:
            used_ports.append(int(edge_data['port'][1]))

    # Get connected valve positions.
    for _, _, edge_data in graph.out_edges(valve_node, data=True):
        if 'port' in edge_data:
            used_ports.append(int(edge_data['port'][0]))

    # Return first found unconnected valve positions.
    for i in range(-1, 6):  # Possible valve ports are -1, 0, 1, 2, 3, 4, 5.
        if i not in used_ports:
            return i

    return None

def vacuum_device_attached_to_flask(
    flask_node: str, graph: MultiDiGraph
) -> bool:
    """Return True if given vacuum flask is attached to a vacuum device. If it
    is attached to nothing (i.e. vacuum line in fumehood) return False.

    Args:
        flask_node (str): Name of vacuum flask node.
        graph (MultiDiGraph): Graph containing flask_node.

    Returns:
        bool: True if vacuum flask is attached to vacuum device not just vacuum
            line in fumehood.
    """
    for src_node, _ in graph.in_edges(flask_node):
        if graph.nodes[src_node]['class'] in VACUUM_CLASSES:
            return src_node
    return None

def graph_hash(graph: MultiDiGraph):
    """Get hash of graph."""
    # Get relevant data in sorted form. This allows x, y positions etc to be
    # changed without affecting the graph hash.

    nodes = []
    sorted_nodes = sorted(graph.nodes(), key=lambda node: str(node))
    for node in sorted_nodes:
        node_props = []
        graph_node = graph.nodes[node]

        if 'chemical' in graph_node:
            node_props.append(['chemical', graph_node['chemical']])
        if 'max_volume' in graph_node:
            node_props.append(['max_volume', graph_node['max_volume']])
        if 'dead_volume' in graph_node:
            node_props.append(['dead_volume', graph_node['dead_volume']])

        nodes.append([str(node), node_props])

    edges = []
    for src, dest, data in graph.edges(data=True):
        if 'port' in data:
            port = data['port']
            if type(data['port']) == str:
                port = port[1:-1].split(',')

            port_str = f"({str(port[0])},{str(port[1])})".replace(' ', '')
        else:
            port_str = '(,)'
        edges.append(f'{str(src)}@@@{str(dest)}@@@{port_str}')
    edges = sorted(edges)
    hash_str = json.dumps(
        {'nodes': nodes, 'edges': edges}, separators=(',', ':'))
    return hashlib.sha256(
        hash_str.encode('utf-8')
    ).hexdigest()
