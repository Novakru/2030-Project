"""
.. module:: graphgen.apply_graph_spec
    :platform: Unix, Windows
    :synopsis: Takes the spec of what the graph should ne like and alters
                the template grpah accordingly

"""
from typing import List, Tuple, Optional, Union, Dict
from networkx import MultiDiGraph
from xdl.utils.graph import undirected_neighbors
from xdl.constants import INERT_GAS_SYNONYMS
from .constants import (
    GRIDSIZE,
    DEFAULT_BUFFER_FLASK_VOLUME,
    DEFAULT_REAGENT_FLASK_VOLUME
)
from .utils import (
    get_backbone_valve,
    get_new_edge_id,
    get_new_node_id,
    get_nearest_unused_ports,
    get_pre_existing_flasks,
    get_pre_existing_cartridges,
)
from .optimize_graph import (
    get_optimal_arrangement,
    cartridge_in_pseudo_flask_name,
    cartridge_out_pseudo_flask_name
)
from ..utils.execution import (
    get_backbone, graph_flasks, graph_valves, get_unused_valve_port)
from ..constants import (
    VACUUM_CLASSES,
    CHEMPUTER_VACUUM,
    CHEMPUTER_VALVE,
    CHEMPUTER_PUMP,
    CHEMPUTER_WASTE,
    CHILLER_CLASSES,
    COMPONENT_CLASS_TYPE_DICT,
    CVC3000
)

def preprocess_graph(graph: MultiDiGraph, graph_spec: Dict) -> Dict:
    """Preprocess graph by removing unnecessary nodes.

    Args:
        graph (MultiDiGraph): Graph to preprocess
        graph_spec (Dict): Graph specification

    Returns:
        Dict: Preprocessed graph
    """

    remove_unused_modules(graph, graph_spec)
    return graph

def postprocess_graph(graph: MultiDiGraph) -> Dict:
    """Tidy graph by improving spacing between nodes.

    Args:
        graph (MultiDiGraph): Graph to postprocess

    Returns:
        Dict: Postprocessed graph
    """

    tidy_graph(graph)
    return graph

def tidy_graph(graph: MultiDiGraph) -> Dict:
    """Tidy graph by improving spacing between nodes.

    Args:
        graph (MultiDiGraph): Graph to tidy

    Returns:
        Dict: Tidied graph
    """

    trim_backbone(graph)
    shorten_long_single_edges(graph)
    sweep_left_to_right(graph)
    return graph

def trim_backbone(graph: MultiDiGraph):
    """Remove any unused valve on end of backbone.

    Args:
        graph (MultiDiGraph): Graph to trim
    """

    deletions = []
    backbone = get_backbone(graph, ordered=True)

    # Go through backbone from left
    for i in range(len(backbone)):
        should_remove, nodes_to_delete = (
            backbone_valve_has_nothing_attached(graph, backbone, i)
        )

        # Remove the valve
        if should_remove:
            deletions.extend(nodes_to_delete)

        else:
            break

    # Go through backbone from right
    for i in reversed(range(len(backbone))):
        should_remove, nodes_to_delete = backbone_valve_has_nothing_attached(
            graph, backbone, i)

        # Remove the valve
        if should_remove:
            deletions.extend(nodes_to_delete)

        else:
            break

    # Remove all valves from the graph
    for node in deletions:
        graph.remove_node(node)

def backbone_valve_has_nothing_attached(
    graph: MultiDiGraph, backbone: List[str], pos: int
) -> Tuple[bool, List[str]]:
    """Check if backbone valve only has connections to other backbone valves,
    and waste/pump. Return True if so, and a list of the node names of the
    valve / pump / waste for deletion by trim_backbone.

    Args:
        graph (MultiDiGraph): Graph to check
        backbone (List[str]): List of backbone valves
        pos (int): Position in the backbone

    Returns:
        Tuple[bool, List[str]]: If a node should be removed and list of nodes
                                    to remove
    """

    valve = backbone[pos]
    should_remove = True
    nodes_to_delete = []
    neighbors = list(undirected_neighbors(graph, valve, data=True))

    # Quick check to see if end of backbone node has right number of neighbors
    # for nothing being attached
    if pos in [0, len(backbone) - 1] and len(neighbors) != 3:
        return False, []

    # Quick check to see if middle of backbone node has right number of
    # neighbors for nothing being attached
    elif pos > 0 and pos < len(backbone) - 1 and len(neighbors) != 4:
        return False, []

    # Check neighbors are right type for backbone node having nothing attached
    for neighbor, data in neighbors:

        # If valve attached not in backbone, don't treat backbone valve as empty
        if data['class'] == CHEMPUTER_VALVE:
            if neighbor not in backbone:
                should_remove = False
                nodes_to_delete = []
                break

        # Pump and waste should be removed along with empty backbone valve so
        # append to nodes_to_delete
        elif data['class'] in [CHEMPUTER_PUMP, CHEMPUTER_WASTE]:
            nodes_to_delete.append(neighbor)

        # Node found with class other than valve / pump / waste, backbone valve
        # is not empty and shouldn't be removed
        else:
            should_remove = False
            nodes_to_delete = []
            break

    if should_remove:
        nodes_to_delete.append(valve)

    return should_remove, nodes_to_delete

def sweep_left_to_right(graph: MultiDiGraph):
    """Keep relative positioning of nodes while removing unnecessary gaps.

    Args:
        graph (MultiDiGraph): Graph to check
    """
    # Get all columns of nodes along with x values
    columns_dict = {}
    for node, data in graph.nodes(data=True):
        x = data['x']
        if int(x) in columns_dict:
            columns_dict[x].append(node)
        else:
            columns_dict[x] = [node]

    columns = [(x, columns_dict[x]) for x in sorted(columns_dict)]

    # Go through columns and shift everyone left without getting within
    # threshold of the next column
    threshold = 3 * GRIDSIZE
    for i, column in enumerate(columns):

        # At last column, break
        if i == len(columns) - 1:
            break

        # Unpack columns
        x, nodes = column
        next_x, _ = columns[i + 1]

        x_diff = next_x - x

        # There is room to sweep
        if x_diff > threshold:

            # Move nodes in column
            for node in nodes:
                graph.nodes[node]['x'] += x_diff - threshold

            # Move all previous columns
            for _, prev_nodes in columns[:i]:
                for prev_node in prev_nodes:
                    graph.nodes[prev_node]['x'] += x_diff - threshold

def shorten_long_single_edges(graph: MultiDiGraph):
    """If a node has one neighbor and it's edge to this neighbor is huge,
    shorten the edge.

    Args:
        graph (MultiDiGraph): Graph to check
    """
    offset = 3
    for src, dest in graph.edges():
        src_node = graph.nodes[src]
        dest_node = graph.nodes[dest]
        src_x, src_y = src_node['x'], src_node['y']
        dest_x, dest_y = dest_node['x'], dest_node['y']

        # src has 1 neighbor
        if len(list(undirected_neighbors(graph, src))) == 1:

            # src node way off to the right
            if src_x - dest_x > offset * GRIDSIZE:
                src_node['x'] = dest_x + offset * GRIDSIZE

            # src node way off to the left
            elif dest_x - src_x > offset * GRIDSIZE:
                src_node['x'] = dest_x - offset * GRIDSIZE

            # src node way off below
            if src_y - dest_y > offset * GRIDSIZE:
                src_node['y'] = dest_y + offset * GRIDSIZE

            # src node way off above
            elif dest_y - src_y > offset * GRIDSIZE:
                src_node['y'] = dest_y - offset * GRIDSIZE

        # dest has 1 neighbor
        if len(list(undirected_neighbors(graph, dest))) == 1:

            # dest node way off to the right
            if dest_x - src_x > offset * GRIDSIZE:
                dest_node['x'] = src_x + offset * GRIDSIZE

            # dest node way off to the left
            elif src_x - dest_x > offset * GRIDSIZE:
                dest_node['x'] = dest_x - offset * GRIDSIZE

            # dest node way off below
            if dest_y - src_y > offset * GRIDSIZE:
                dest_node['y'] = src_y + offset * GRIDSIZE

            # dest node way off above
            elif src_y - dest_y > offset * GRIDSIZE:
                dest_node['y'] = dest_y - offset * GRIDSIZE

    return graph

def remove_unused_modules(graph: MultiDiGraph, graph_spec: Dict):
    """Remove unused modules from the graph

    Args:
        graph (MultiDiGraph): Graph to check
        graph_spec (Dict): Grtaph specification
    """
    # Get the backbone
    backbone = get_backbone(graph)

    # Get all used module types, e.g. 'reactor', 'filter', etc.
    used_modules = [item[1] for item in graph_spec['vessels']['types']]

    # Iterate through all grpah nodes
    nodes_to_delete = []
    for node, data in graph.nodes(data=True):
        node_class = data['class']
        if node_class in COMPONENT_CLASS_TYPE_DICT:
            node_type = COMPONENT_CLASS_TYPE_DICT[node_class]

            # Node is unused, amrk for deletion
            if node_type not in used_modules:
                nodes_to_delete.append(node)

                # CHeck the node's neighbors
                for neighbor, neighbor_data in undirected_neighbors(
                        graph, node, data=True):
                    if neighbor not in backbone:

                        # If neighbor is vacuum or chiller and is also attached
                        # to another node, don't delete.
                        if (neighbor_data['class'] not in
                            VACUUM_CLASSES + CHILLER_CLASSES
                                or len(graph.out_edges(neighbor)) <= 1):
                            nodes_to_delete.append(neighbor)

    # Remove all nodes marked for deletion
    for node in nodes_to_delete:
        graph.remove_node(node)

    # Remove any orphaned nodes no longer attached
    remove_orphaned_nodes(graph)

def remove_orphaned_nodes(graph: MultiDiGraph):
    """Remove all nodes that aren't associated with any edges.

    Args:
        graph (MultiDiGraph): Graph to check
    """

    # Get non-orphan nodes
    used_nodes = []
    for src, dest in graph.edges():
        used_nodes.append(src)
        used_nodes.append(dest)
    used_nodes = set(used_nodes)

    # Get orphaned nodes
    nodes_to_delete = [
        node for node in graph.nodes() if node not in used_nodes
    ]

    # Also get ChemputerVacuum nodes attached to CVC3000 with nothing coming in
    for node, data in graph.nodes(data=True):
        if data['class'] == CHEMPUTER_VACUUM:
            neighbors = list(undirected_neighbors(graph, node, data=True))
            if len(neighbors) == 1:
                _, neighbor_data = neighbors[0]
                if neighbor_data['class'] == CVC3000:
                    nodes_to_delete.append(node)

    # Remove orphaned nodes
    for node in nodes_to_delete:
        graph.remove_node(node)

    return graph

def apply_spec_to_template(
    xdl_obj, graph_spec: Dict, graph: MultiDiGraph, fixable_issues: List
) -> Dict:
    """Apply the given graph specification to the template graph

    Args:
        xdl_obj (XDL): XDL object
        graph_spec (Dict): Graph specification
        graph (MultiDiGraph): Graph to check
        fixable_issues (List): Any issues that can be fixed

    Returns:
        Dict: Graph with applied spec
    """

    preprocess_graph(graph, graph_spec)
    pre_existing_flasks = get_pre_existing_flasks(graph)

    apply_buffer_flasks(graph, graph_spec['buffer_flasks'], pre_existing_flasks)
    apply_reagent_flasks_and_cartridges(
        xdl_obj,
        graph,
        graph_spec['reagents'],
        pre_existing_flasks,
        graph_spec['cartridges']
    )
    postprocess_graph(graph)

    return graph

def apply_buffer_flasks(
    graph: MultiDiGraph, buffer_flask_spec: Dict, pre_existing_flasks: Dict
):
    """Apply buffer flasks from the specification to the graph

    Args:
        graph (MultiDiGraph): Grpah to modify
        buffer_flask_spec (Dict): Buffer flask specification
        pre_existing_flasks (Dict): Pre existing buffer flasks in the graph
    """

    if buffer_flask_spec:
        n_buffer_flasks_required = max(
            buffer_flask_spec,
            key=lambda item: item['n_required']
        )['n_required']
    else:
        return

    # Use existing buffer flasks if possible
    buffer_flasks_added = 0
    for chemical, node in pre_existing_flasks.items():
        if not chemical:
            if buffer_flasks_added < n_buffer_flasks_required:
                buffer_flasks_added += 1
            else:
                graph.remove_node(node)
    if buffer_flasks_added >= n_buffer_flasks_required:
        return

    # Add new buffer flasks if necessary
    for buffer_flask in buffer_flask_spec:
        # Get the node connected to the flask
        connected_node = buffer_flask['connected_node']

        # Get the total number of flasks required
        n_required = buffer_flask['n_required']

        # Iterate over how many flasks required
        for _ in range(n_required):
            if connected_node is not None:
                # Get the valve connected to flask from the backbone
                connected_valve = get_backbone_valve(graph, connected_node)
            else:
                connected_valve = get_backbone(graph)[0]

            # Get the valve and nearest unused port
            connected_valve, unused_ports = get_nearest_unused_ports(
                graph, connected_valve
            )

            # Give flask default name
            buffer_flask_name = f'buffer_flask{buffer_flasks_added+1}'

            # Add the flask
            add_buffer_flask(
                graph,
                buffer_flask_name,
                connected_valve,
                unused_ports[0]
            )

            # Add graph edges for the flask
            add_buffer_flask_edges(
                graph, connected_valve, buffer_flask_name, unused_ports[0])

            # Increment number of flasks added
            buffer_flasks_added += 1
            if buffer_flasks_added >= n_buffer_flasks_required:
                return

def get_used_node_positions(graph: dict) -> List[str]:
    """Obtain a list of positions used by nodes in the graph

    Args:
        graph (dict): Graph to modify

    Returns:
        List[str]: List of used positions by nodes
    """

    # List for the positions
    used_pos = []

    # Iterate through the graph
    for _, data in graph.nodes(data=True):
        # Add positions to list if they exist
        used_pos.append((data['x'], data['y']))

    return used_pos

def get_flask_position(graph, valve, port):
    """Get flask position based on the valve and port it is attached to."""
    used_pos = get_used_node_positions(graph)

    # Get the valve's X and Y coords
    valve_x = graph.nodes[valve]['x']
    valve_y = graph.nodes[valve]['y']
    offset = GRIDSIZE * 2
    possible_pos = [
        (valve_x - offset, valve_y - offset),
        (valve_x - offset, valve_y + offset),
        (valve_x, valve_y + 2 * offset),
        (valve_x + offset, valve_y + offset),
        (valve_x + offset, valve_y - offset),
        (valve_x - offset, valve_y),
        (valve_x + offset, valve_y),
    ]

    # Try to return position that matches actual setup of valve, so going
    # anticlockwise from NW to SE through ports 2, 3, 4 and 5.
    if str(port) == '2' and possible_pos[0] not in used_pos:
        return possible_pos[0]

    if str(port) == '3' and possible_pos[1] not in used_pos:
        return possible_pos[1]

    elif str(port) == '4' and possible_pos[2] not in used_pos:
        return possible_pos[2]

    elif str(port) == '5' and possible_pos[3] not in used_pos:
        return possible_pos[3]

    # If ideal position for port already used, just return available position.
    for pos in possible_pos:
        # Position unused, return
        if pos not in used_pos:
            return pos

    # Return default
    return (0, 0)

def add_buffer_flask(graph, node_name, valve, port):
    x, y = get_flask_position(graph, valve, port)
    graph.add_node(
        node_name,
        **{
            'class': 'ChemputerFlask',
            'type': 'flask',
            'x': x,
            'y': y,
            'id': node_name,
            'label': node_name,
            'name': node_name,
            'max_volume': DEFAULT_BUFFER_FLASK_VOLUME,
            'current_volume': 0,
            'chemical': '',
            'internalId': get_new_node_id(graph),
        }
    )

def add_buffer_flask_edges(
    graph: dict, valve: str, flask: str, valve_port: str
):
    """Adds graph edges to the newly added buffer flasks

    Args:
        graph (dict): Graph to modify
        valve (str): Valve attached to buffer flask
        flask (str): Buffer flask
        valve_port (str): Port on the valve that's attached to the flask
    """

    # Get the flask and valve ID
    flask_id = graph.nodes[flask]['internalId']
    valve_id = graph.nodes[valve]['internalId']

    # Define new data to add for inward connections
    in_data = {
        'id': get_new_edge_id(graph),
        'source': valve,
        'target': flask,
        'sourceInternal': valve_id,
        'targetInternal': flask_id,
        'port': [valve_port, 0]
    }

    # Add inward edge
    graph.add_edge(valve, flask, **in_data)

    # Define new data to add for outward connections
    out_data = {
        'id': get_new_edge_id(graph),
        'source': flask,
        'target': valve,
        'sourceInternal': flask_id,
        'targetInternal': valve_id,
        'port': [0, valve_port]
    }

    # Add outward edge
    graph.add_edge(flask, valve, **out_data)

def apply_reagent_flasks_and_cartridges(
        xdl_obj, graph, reagent_spec, pre_existing_flasks, cartridges):
    if not reagent_spec:
        return

    flasks = {}
    inert_gas_flask = None
    inert_gas = None

    # Add inert gas flasks
    for node, data in graph_flasks(graph, data=True):
        if data['chemical'] in INERT_GAS_SYNONYMS:
            inert_gas_flask = node
            inert_gas = data['chemical']

    graph.remove_node(inert_gas_flask)

    # Delete unused pre existing flasks
    for chemical, node in pre_existing_flasks.items():
        if chemical not in reagent_spec:
            graph.remove_node(node)
        else:
            reagent_spec.remove(chemical)
            flasks[chemical] = node

    # Add extra reagent flasks needed
    for reagent in reagent_spec:
        flasks[reagent] = f'flask_{reagent}'
    flask_reagent_dict = {v: k for k, v in flasks.items()}
    if inert_gas_flask:
        flask_reagent_dict[inert_gas_flask] = inert_gas

    # Get optimal arrangement of flasks
    optimal_arrangement = get_optimal_arrangement(
        xdl_obj, graph, flasks, inert_gas_flask, cartridges)

    # Add flasks in optimal positions
    backbone = get_backbone(graph, ordered=True)

    apply_cartridge(graph, cartridges, optimal_arrangement)

    for flask_name, position in optimal_arrangement.items():
        # Skip cartridges
        if '-cartridge-' in flask_name:
            continue

        backbone_index, port = position
        valve = backbone[backbone_index]
        add_reagent_flask(
            graph,
            valve,
            port,
            flask_name,
            flask_reagent_dict[flask_name]
        )
        add_reagent_flask_edge(
            graph,
            valve,
            flask_name,
            port,
        )

    # Remake inert gas to module vacuum/flask valves connections
    if inert_gas_flask:
        for valve in graph_valves(graph):
            if valve not in backbone:
                add_reagent_flask_edge(
                    graph,
                    valve,
                    flask_name,
                    get_unused_valve_port(graph, valve)
                )


def add_reagent_flask(graph, valve, port, node_name, reagent):
    x, y = get_flask_position(graph, valve, port)
    graph.add_node(node_name, **{
        'type': 'flask',
        'x': x,
        'y': y,
        'max_volume': DEFAULT_REAGENT_FLASK_VOLUME,
        'current_volume': 0,
        'class': 'ChemputerFlask',
        'chemical': reagent,
        'name': node_name,
        'label': node_name,
        'id': node_name,
        'internalId': get_new_node_id(graph)
    })

def add_reagent_flask_edge(
    graph: dict, valve: str, flask: str, valve_port: str
):
    """Adds the appropriate edges to the new flask node in the graph

    Args:
        graph (dict): Grpah to modify
        valve (str): Valve to attach to new flask
        flask (str): New reagent flask
        valve_port (str): Port to attach the flask to
    """

    # Get the ID of the valve and flask
    valve_id = graph.nodes[valve]['internalId']
    flask_id = graph.nodes[flask]['internalId']

    # Add Outward edge from flask to valve
    graph.add_edge(flask, valve, **{
        'port': [0, valve_port],
        'source': flask,
        'target': valve,
        'sourceInternal': flask_id,
        'targetInternal': valve_id,
        'id': get_new_edge_id(graph),
    })

def get_cartridge_node_position(
    graph: dict, from_valve: str, to_valve: str
) -> Tuple[int, int]:
    """Get the position of a Cartridge node

    Args:
        graph (dict): Graph to modify
        from_valve (str): From valve
        to_valve (str): To valve

    Returns:
        Tuple[int, int]: Coords of the cartridge
    """

    # Used positions
    used_positions = []

    # Iterate through the graph
    for node, data in graph.nodes(data=True):
        # Add any used positions in the graph
        used_positions.append((data['x'], data['y']))

    # Get the X and Y coord of the from_valve
    from_x = graph.nodes[from_valve]['x']
    from_y = graph.nodes[from_valve]['y']

    # Get the X and Y coords of the to_valve
    to_x = graph.nodes[to_valve]['x']
    to_y = graph.nodes[to_valve]['y']

    # Calculate minimum & maximum distance between from and to valve
    min_x = min(from_x, to_x)
    min_y = min(from_y, to_y)
    max_x = max(from_x, to_x)
    pos = (min_x + ((max_x - min_x) / 2), min_y - 4 * GRIDSIZE)
    while pos in used_positions:
        pos = (pos[0] + 80, pos[1])

    # Return position
    return pos

def get_nearest_buffer_flask_valve(graph: dict, backbone_valve: str) -> str:
    """Gets the nearest buffer flask on the given valve

    Args:
        graph (dict): Grahm to check
        backbone_valve (str): Backbone valve of flask

    Returns:
        str: Buffer flask
    """

    # Get all the backbone valves
    backbone_valves = get_backbone(graph)

    # Get all buffer flasks
    buffer_flasks = get_buffer_flasks_on_valve(graph, backbone_valve)

    # Found buffer flasks, return first one
    if buffer_flasks:
        return buffer_flasks[0]

    # Set list to avoid this valve
    avoid = [backbone_valve]

    # Get all buffer flasks from neighboring valves
    buffer_flasks, tried = get_buffer_flasks_from_neighbors(
        graph, backbone_valve, avoid
    )

    # Found buffer flasks, return first one
    if buffer_flasks:
        return buffer_flasks[0]

    # Add neighboring valve to avoid list
    avoid.extend(tried)

    # Loop so long as avoid is shorter than number of backbone valves
    while (len([item for item in avoid if item in backbone_valves])
           < len(backbone_valves)):

        # Iterate through valves
        for valve in tried:
            # Valve is in the backbome
            if valve in backbone_valves:
                # Get all buffer flasks from neighboring valves
                buffer_flasks, tried = get_buffer_flasks_from_neighbors(
                    graph, backbone_valve, avoid
                )

                # Found buffer flasks, return first one
                if buffer_flasks:
                    return buffer_flasks[0]

                # Add valve to avoid list
                avoid.extend(tried)

def get_buffer_flasks_from_neighbors(
    graph: dict, valve: str, avoid: Optional[List[str]] = []
) -> Union[Optional[List[str]], Optional[List[str]]]:
    """Get any buffer flasks from neighboring valves

    Args:
        graph (dict): Graph to search through
        valve (str): Valve to check for buffer flasks
        avoid (Optional[List[str]], optional): List of valves to avoid.
                                                Defaults to [].

    Returns:
        Union[Optional[List[str]], Optional[List[str]]]: Buffer flasks if any,
                                    and any attempted valves.
    """

    # Lists to track buffer flasks and tried valves
    buffer_flasks, tried = [], []

    # Iterate through all neighboring nodes of the given valve (Undirected)
    for neighbor in undirected_neighbors(graph, valve):
        # Node is a ChemputerValve
        if graph.nodes[neighbor]['class'] == 'ChemputerValve':
            # Add any buffer flasks found
            buffer_flasks.extend(get_buffer_flasks_on_valve(graph, neighbor))

            # Add valve to attempted list
            tried.append(neighbor)

    # Return flasks and any attempted valves
    return buffer_flasks, tried

def get_buffer_flasks_on_valve(graph: dict, valve: str) -> Optional[List[str]]:
    """Find any buffer flasks attached to a given valve

    Args:
        graph (dict): Graph to check
        valve (str): Valve to search

    Returns:
        Optional[List[str]]: Buffer flasks attached to valve
    """

    # List to hold any located flasks
    buffer_flasks = []

    # Iterate through all neighbouring nodes to the valve (Undirected)
    for node in undirected_neighbors(graph, valve):
        # Node is a ChemputerFlask with no chemical assigned
        if (graph.nodes[node]['class'] == 'ChemputerFlask'
                and not graph.nodes[node]['chemical']):

            # Add flask to list
            buffer_flasks.append(node)

    # Reutrn buffer flask list
    return buffer_flasks

def apply_cartridge(graph, cartridge_spec, optimal_arrangement):
    existing_cartridges = get_pre_existing_cartridges(graph)
    for i in reversed(range(len(cartridge_spec))):
        chemical = cartridge_spec[i]['chemical']
        if chemical in existing_cartridges:
            cartridge_spec.pop(i)
            del existing_cartridges[chemical]

    existing_cartridge_nodes = list(existing_cartridges.values())

    # Delete extra cartridges
    n_to_delete = len(existing_cartridge_nodes) - len(cartridge_spec)
    deleted = 0
    while deleted < n_to_delete:
        graph.remove_node(existing_cartridge_nodes.pop())
        deleted += 1

    for cartridge in cartridge_spec:
        # Try to use existing cartridge
        if existing_cartridge_nodes:
            graph.nodes[existing_cartridge_nodes.pop()][
                'chemical'] = cartridge['chemical']
            continue

        backbone = get_backbone(graph, ordered=True)

        # Make new cartridge
        chemical = cartridge['chemical']
        optimal_in = optimal_arrangement[
            cartridge_in_pseudo_flask_name(chemical)]
        optimal_out = optimal_arrangement[
            cartridge_out_pseudo_flask_name(chemical)]
        from_valve = backbone[optimal_in[0]]
        to_valve = backbone[optimal_out[0]]

        # Assign default name
        cartridge_node_name = f'cartridge_{chemical}'

        # Add a new ID for the cartridge
        cartridge_internal_id = get_new_node_id(graph)

        # Make in edge
        in_edge_data = {
            'id': get_new_edge_id(graph),
            'port': [optimal_in[1], 'in'],
            'source': from_valve,
            'target': cartridge_node_name,
            'sourceInternal': graph.nodes[from_valve]['internalId'],
            'targetInternal': cartridge_internal_id,
        }

        # Make out edge
        out_edge_data = {
            'id': None,
            'port': ['out', optimal_out[1]],
            'source': cartridge_node_name,
            'target': to_valve,
            'sourceInternal': cartridge_internal_id,
            'targetInternal': graph.nodes[to_valve]['internalId'],
        }

        # Get a position for the cartridge and apply to node
        x, y = get_cartridge_node_position(graph, from_valve, to_valve)
        node_data = {
            'id': cartridge_node_name,
            'label': cartridge_node_name,
            'name': cartridge_node_name,
            'chemical': chemical,
            'type': 'cartridge',
            'class': 'ChemputerCartridge',
            'internalId': cartridge_internal_id,
            'x': x,
            'y': y
        }

        # Add node and edges for new cartridge
        graph.add_node(cartridge_node_name, **node_data)
        graph.add_edge(from_valve, cartridge_node_name, **in_edge_data)
        out_edge_data['id'] = get_new_edge_id(graph)
        graph.add_edge(cartridge_node_name, to_valve, **out_edge_data)

def add_edges(graph, src, dest, src_port, dest_port, bidirectional=False):
    """Add edge between two given nodes and ports, or two edges if bidirectional
    is True.
    """
    src_id = graph.nodes[dest]['internalId']
    dest_id = graph.nodes[src]['internalId']
    in_data = {
        'id': get_new_edge_id(graph),
        'source': src,
        'target': dest,
        'sourceInternal': dest_id,
        'targetInternal': src_id,
        'port': [src_port, dest_port]
    }
    graph.add_edge(src, dest, **in_data)

    if bidirectional:
        out_data = {
            'id': get_new_edge_id(graph),
            'source': dest,
            'target': src,
            'sourceInternal': src_id,
            'targetInternal': dest_id,
            'port': [dest_port, src_port]
        }
        graph.add_edge(dest, src, **out_data)
