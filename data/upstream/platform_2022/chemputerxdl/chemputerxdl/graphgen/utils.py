"""
.. module:: graphgen.utils
    :platform: Unix, Windows
    :synopsis: Utilities for the graphgen module

"""
from typing import Tuple, Dict, Optional, List, Union
from networkx import MultiDiGraph

# XDL
from xdl.utils.graph import undirected_neighbors
from xdl.constants import INERT_GAS_SYNONYMS

# Relative
from .constants import GRIDSIZE
from ..constants import (
    CHEMPUTER_FLASK,
    CHEMPUTER_CARTRIDGE,
    CHEMPUTER_VALVE,
    CHEMPUTER_PUMP,
    CHEMPUTER_WASTE,
)
from ..utils.execution import (
    get_backbone,
    get_unused_valve_port,
    get_waste_on_valve,
    get_pump_on_valve,
)

def get_backbone_valve(graph: MultiDiGraph, node: str) -> Optional[str]:
    """Gets a valve that is apart of the backbone

    Args:
        graph (networkx.MultiDiGraph): Graph to check
        node (str): Node to fetch the valve from

    Returns:
        Optional[str]: Target valve
    """

    # Iterate through all neighbors of the node
    for neighbor in undirected_neighbors(graph, node):
        # Found a valve
        if graph.nodes[neighbor]['class'] == CHEMPUTER_VALVE:
            # Only look for valve with pump attached
            for valve_neighbor in graph.neighbors(neighbor):
                if graph.nodes[valve_neighbor]['class'] == CHEMPUTER_PUMP:
                    return neighbor
    # Can't find valve
    return None

def get_valve_unused_ports(graph: MultiDiGraph, valve: str) -> List[str]:
    """Get all unused ports on a valve

    Args:
        graph (networkx.MultiDiGraph): Graph to search
        valve (str): Valve to find unused ports

    Returns:
        List[str]: List of unused port
    """

    used_ports = []

    # Iterate through all graph edges
    for src, dest, data in graph.edges(data=True):
        # Src is target valve
        if src == valve:
            # Get all ports and add src to used
            src_port, dest_port = data['port']
            used_ports.append(src_port)

        # Dest is target valve
        elif dest == valve:
            # Get all ports and add dest to used
            src_port, dest_port = data['port']
            used_ports.append(dest_port)

    # Return list of ports that are not in the used port list
    return [str(i) for i in range(6) if str(i) not in used_ports]

def get_new_edge_id(graph: MultiDiGraph) -> int:
    """Get a new ID number for an edge

    Args:
        graph (networkx.MultiDiGraph): Graph to search

    Returns:
        int: New graph ID
    """

    # Hold all used ID numbers
    used_edge_ids = []

    # Iterate through all graph edges
    for _, _, data in graph.edges(data=True):
        # Add any ID present
        used_edge_ids.append(data['id'])

    # Increment counter until new ID reached
    i = 0
    while i in used_edge_ids:
        i += 1

    # Return new ID
    return i

def get_new_node_id(graph: MultiDiGraph) -> int:
    """Get a new ID for a graph node

    Args:
        graph (networkx.MultiDiGraph): Graph to search

    Returns:
        int: New node ID
    """

    # List to hold all previously seen node IDs
    used_node_ids = []

    # Iterate through all nodes
    for _, data in graph.nodes(data=True):
        # Get all used IDs
        used_node_ids.append(data['internalId'])

    # Increment counter until new ID reached
    i = 0
    while i in used_node_ids:
        i += 1

    # Return new ID
    return i

def get_nearest_unused_ports(
    graph: MultiDiGraph, valve: str, avoid: Optional[List[str]] = []
) -> Tuple[str, List[str]]:
    """Gets the nearest unused ports to a valve

    Args:
        graph (networkx.MultiDiGraph): Graph to search
        valve (str): Target valve to find ports
        avoid (Optional[List[str]], optional): Nodes to avoid. Defaults to [].

    Returns:
        Tuple[str, List[str]]: Valve name and unused ports
    """

    # Get all unused ports and backbone valves
    unused_ports = get_valve_unused_ports(graph, valve)
    backbone_valves = get_backbone(graph)

    # Have no unused ports
    if not unused_ports:
        # Iterate through all neighbors of the valve
        for neighbor in undirected_neighbors(graph, valve):
            # neighbor is in the backbone and not to be avoided
            if neighbor in backbone_valves and neighbor not in avoid:
                # Get it's unused ports
                unused_ports = get_valve_unused_ports(graph, neighbor)

                # Unused ports, set valve to neighbor
                if unused_ports:
                    valve = neighbor
                    break

    # No unused ports
    if not unused_ports:
        # Iterate through all backbone valves
        for backbone_valve in backbone_valves:
            # Valve is not to be avoided
            if backbone_valve not in avoid:
                # Get unused ports
                unused_ports = get_valve_unused_ports(graph, backbone_valve)

                # Unused ports are found, set valve to backbone valves
                if unused_ports:
                    valve = backbone_valve
                    break

    # Return valve and unused ports
    return valve, unused_ports

def get_pre_existing_flasks(graph: MultiDiGraph) -> Dict[str, str]:
    """Get all reagents flasks that are already in graph.
    Args:
        graph (networkx.MultiDiGraph): Graph to look for reagent flasks in.

    Returns:
        Dict[str, str]: Dict of { chemical: node_name } for all reagent flasks
            found in graph.
    """
    pre_existing_flasks = {}
    for node in graph.nodes():
        full_node = graph.nodes[node]
        if (full_node['class'] == CHEMPUTER_FLASK
                and full_node['chemical'].lower() not in INERT_GAS_SYNONYMS):
            pre_existing_flasks[full_node['chemical']] = node
    return pre_existing_flasks

def get_pre_existing_cartridges(graph: MultiDiGraph) -> List[str]:
    """Get all cartridges that are already in graph.

    Args:
        graph (networkx.MultiDiGraph): Graph to look for cartridges in.

    Returns:
        Dict[str, str]: Dict of { chemical: node_name } for all cartridges found
            in graph.
    """
    cartridges = {}
    for node, data in graph.nodes(data=True):
        if data['class'] == CHEMPUTER_CARTRIDGE:
            cartridges[data['chemical']] = node
    return cartridges

def extend_backbone(graph: MultiDiGraph, extra_valves: int) -> None:
    """Extend backbone on right end by adding extra valves. For each valves add
    a pump, waste and necessary edges.

    Args:
        graph (networkx.MultiDiGraph): Graph to extend backbone on.
        extra_valves (int): Number of valves to add to backbones.
    """
    backbone = get_backbone(graph, ordered=True)
    end_valve = backbone[-1]
    end_valve_data = graph.nodes[end_valve]
    for i in range(extra_valves):
        # Valve
        new_valve_name = f'extend-valve-{i + 1}'
        new_valve_data = {
            'type': 'valve',
            'class': CHEMPUTER_VALVE,
            'x': end_valve_data['x'] + GRIDSIZE * 6,
            'y': end_valve_data['y'],
            'internalId': get_new_node_id(graph),
            'name': new_valve_name,
            'id': new_valve_name,
            'label': new_valve_name,
            'address': '',
        }
        graph.add_node(new_valve_name, **new_valve_data)

        # Waste
        end_valve_waste = get_waste_on_valve(graph, end_valve)
        end_valve_waste_data = graph.nodes[end_valve_waste]
        new_waste_name = f'extend-waste-{i + 1}'
        new_waste_data = {
            'type': 'waste',
            'class': CHEMPUTER_WASTE,
            'x': end_valve_waste_data['x'] + GRIDSIZE * 6,
            'y': end_valve_waste_data['y'],
            'internalId': get_new_node_id(graph),
            'name': new_waste_name,
            'id': new_waste_name,
            'label': new_waste_name,
            'current_volume': end_valve_waste_data['current_volume'],
            'max_volume': end_valve_waste_data['max_volume']
        }
        graph.add_node(new_waste_name, **new_waste_data)

        # Pump
        end_valve_pump = get_pump_on_valve(graph, end_valve)
        end_valve_pump_data = graph.nodes[end_valve_pump]
        new_pump_name = f'extend-pump-{i + 1}'
        new_pump_data = {
            'type': 'pump',
            'class': CHEMPUTER_PUMP,
            'x': end_valve_pump_data['x'] + GRIDSIZE * 6,
            'y': end_valve_pump_data['y'],
            'internalId': get_new_node_id(graph),
            'name': new_pump_name,
            'id': new_pump_name,
            'label': new_pump_name,
            'current_volume': end_valve_pump_data['current_volume'],
            'max_volume': end_valve_pump_data['max_volume'],
            'address': ''
        }
        graph.add_node(new_pump_name, **new_pump_data)

        # Add edges
        end_valve_unused_port = get_unused_valve_port(graph, end_valve)

        add_edge(graph, new_valve_name, new_waste_name, 0, 0)
        add_edge(graph, new_valve_name, new_pump_name, -1, 0)
        add_edge(graph, new_pump_name, new_valve_name, 0, -1)
        add_edge(graph, new_valve_name, end_valve, 1, end_valve_unused_port)
        add_edge(graph, end_valve, new_valve_name, end_valve_unused_port, 1)

        end_valve = new_valve_name
        end_valve_data = graph.nodes[end_valve]

def add_edge(
    graph: MultiDiGraph,
    src: str,
    dest: str,
    src_port: Union[int, str],
    dest_port: Union[int, str]
) -> None:
    """Create new edge on graph between given nodes with given ports.

    Args:
        graph (networkx.MultiDiGraph): Graph to add edge to.
        src (str): Source node of edge.
        dest (str): Target node of edge.
        src_port (Union[str, int]): Port of edge on source node.
        dest_port (Union[str, int]): Port of edge on target node.
    """
    graph.add_edge(src, dest, **get_new_edge_data(
        graph, src, dest, src_port, dest_port
    ))

def get_new_edge_data(
    graph: MultiDiGraph,
    src: str,
    dest: str,
    src_port: Union[int, str],
    dest_port: Union[int, str]
) -> Dict:
    """Get data for creating a new edge.

    Args:
        graph (networkx.MultiDiGraph): Graph edge will be added to.
        src (str): Source node of edge.
        dest (str): Target node of edge.
        src_port (Union[str, int]): Port of edge on source node.
        dest_port (Union[str, int]): Port of edge on target node.

    Returns:
        Dict: Dict that can be used as edge_data for creating a new edge e.g.
            graph.add_edge(src, dest, **edge_data)
    """
    return {
        'id': get_new_edge_id(graph),
        'port': [src_port, dest_port],
        'source': src,
        'target': dest,
        'sourceInternal': graph.nodes[src]['internalId'],
        'targetInternal': graph.nodes[dest]['internalId']
    }
