"""
.. module:: graphgen.check_graph_spec
    :platforms: Windows, Unix
    :synopsis: Checks the graph specification is correct

"""

from typing import List, Optional, Union, Tuple

# XDL
from xdl.constants import INERT_GAS_SYNONYMS
from xdl.utils.graph import undirected_neighbors

# Relative
from .utils import (
    get_pre_existing_flasks,
    get_pre_existing_cartridges
)
from .constants import (
    HEATER_CHILLER_TEMP_RANGES,
    REMOVE_SRC_PORT,
    REMOVE_DEST_PORT,
    SRC_PORT_INVALID,
    DEST_PORT_INVALID,
    SWITCH_TO_IN_EDGE,
    SWITCH_TO_OUT_EDGE,
    ADD_CHILLER_TO_REACTOR,
    NOT_ENOUGH_SPARE_PORTS,

    CANNOT_REACH_TARGET_TEMP_ERROR,
    INVALID_PORT_ERROR,
    MISSING_COMPONENT_TYPE_ERROR,
    MISSING_HEATER_OR_CHILLER_ERROR,
)
from ..utils.execution import get_backbone
from ..constants import (
    VALID_PORTS,
    CHILLER_CLASSES,
    IKA_RV_10,
    CHEMPUTER_FILTER,
    CHEMPUTER_SEPARATOR,
    CHEMPUTER_REACTOR,
)

def check_graph_spec(
    graph_spec: dict, graph: dict
) -> Union[Optional[List[str]], Optional[List[str]]]:
    """Checks the current graph specification and finds any fixable issues
    and errors.

    Args:
        graph_spec (dict): Graph specification
        graph (dict): Graph to check

    Returns:
        Union[Optional[List[str]], Optional[List[str]]]: Fixable issues if any
                                        and errors if any.
    """
    fixable_issues, errors = [], []

    # Check template graph and find any issues/errors
    template_fixable_issues, template_errors = check_template(graph)
    fixable_issues += template_fixable_issues
    errors += template_errors

    # Check space for cartridges and get any issues/errors
    cartridge_fixable_issues, cartridge_errors = check_cartridges(
        graph_spec['cartridges'], graph
    )
    fixable_issues += cartridge_fixable_issues
    errors += cartridge_errors

    # Check enough flasks for reagents and buffer flasks
    # Get any issues/errors
    flask_fixable_issues, flask_errors = check_flasks(
        graph_spec['reagents'],
        graph_spec['buffer_flasks'],
        graph_spec['cartridges'],
        graph
    )
    fixable_issues += flask_fixable_issues
    errors += flask_errors

    # Check vessels can be heated/chilled to required temps
    # Get any issues/errors
    vessel_fixable_issues, vessel_errors = check_vessel_spec(
        graph_spec['vessels'], graph)
    fixable_issues += vessel_fixable_issues
    errors += vessel_errors

    # Return any fixable issues and errors
    return fixable_issues, errors

def check_template(
    graph: dict
) -> Union[Optional[List[str]], Optional[List[str]]]:
    """Check the template graph for any errors and fixable issues

    Args:
        graph (dict): Template graph

    Returns:
        Union[Optional[List[str]], Optional[List[str]]]: Fixable issues
                                                            and errors
    """

    # Lists for issues and errors
    fixables_issues, errors = [], []

    # Check all template ports for errors
    port_fixable_issues, port_errors = check_template_ports(graph)
    fixables_issues += port_fixable_issues
    errors += port_errors

    # Check all graph edges for errors
    edge_fixable_issues, edge_errors = check_template_edges(graph)
    fixables_issues += edge_fixable_issues
    errors += edge_errors

    # Return fixable issues and errors
    return fixables_issues, errors

def check_template_ports(
    graph: dict
) -> Union[Optional[List[str]], Optional[List[str]]]:
    """Check all ports on the tempalte graph for errors

    Args:
        graph (dict): Template graph

    Returns:
        Union[Optional[List[str]], Optional[List[str]]]: Fixable issues
                                            and errors with template graph ports
    """

    # Lists for fixable issues and errors
    fixable_issues, errors = [], []

    # Iterate through all edges in the graph
    for src, dest, data in graph.edges(data=True):
        # Unpack edge
        src_port, dest_port = data['port']
        src_node = graph.nodes[src]
        dest_node = graph.nodes[dest]
        src_class = src_node['class']
        dest_class = dest_node['class']

        # Find port errors
        src_port_fixables_issues, src_port_errors = check_port(
            'src', src, dest, src_port, dest_port, src_class, dest_class)
        dest_port_fixables_issues, dest_port_errors = check_port(
            'dest', src, dest, src_port, dest_port, src_class, dest_class)

        # Add port errors to lists
        fixable_issues += src_port_fixables_issues
        fixable_issues += dest_port_fixables_issues
        errors += src_port_errors
        errors += dest_port_errors

    # Return fixable issues and errors
    return fixable_issues, errors

def check_port(
    src_or_dest: str,
    src: str,
    dest: str,
    src_port: str,
    dest_port: str,
    src_class: str,
    dest_class: str
) -> Union[Optional[List[str]], Optional[List[str]]]:
    """Checks ports are valid and finds any issues and/or errors

    Args:
        src_or_dest (str): Source or destination node name
        src (str): Source node name
        dest (str): Destinatioon node name
        src_port (str): Source node port
        dest_port (str): Destination node port
        src_class (str): Class of the source node
        dest_class (str): Class of the destination node

    Raises:
        ValueError: Src or dest have to be passed as an argument to src_or_dest

    Returns:
        Union[Optional[List[str]], Optional[List[str]]]: Fixable issues
                                                        and errors
    """

    # Lists for fixable issues and errors
    fixable_issues, errors = [], []

    # Set variables dependent on if src_or_dest is src or dest
    if src_or_dest == 'src':
        port = src_port
        node_class = src_class
    elif src_or_dest == 'dest':
        port = dest_port
        node_class = dest_class

    # Invalid value for src_or_dest
    else:
        raise ValueError(
            'Only "src" or "dest" may be passed as argument src_or_dest'
        )

    # Check src and dest classes are valid for port assignment
    if ((src_class in VALID_PORTS and dest_class in VALID_PORTS)
            or (node_class == 'ChemputerValve')):

        # Get all valid ports for the node
        node_valid_ports = VALID_PORTS[node_class]

        # Port is valid
        if str(port) in node_valid_ports:
            pass

        # Invalid port
        else:
            # More than one valid port, raise error
            if len(node_valid_ports) > 1:
                errors.append({
                    'error': INVALID_PORT_ERROR,
                    'msg': f'{port} is an invalid port for {node_class}. Valid\
 ports: {", ".join(node_valid_ports)}'
                })

            # Only one valid port, offer to fix automatically
            else:
                if src_or_dest == 'src':
                    issue = SRC_PORT_INVALID
                else:
                    issue = DEST_PORT_INVALID
                fixable_issues.append({
                    'src': src,
                    'dest': dest,
                    'src_port': src_port,
                    'dest_port': dest_port,
                    'issue': issue,
                    'msg': f'{port} is an invalid port for {node_class}. Valid\
 ports: {", ".join(node_valid_ports)}'
                })

    # port shouldn't be specified
    else:
        if port:
            if src_or_dest == 'src':
                issue = REMOVE_SRC_PORT
            else:
                issue = REMOVE_DEST_PORT
            fixable_issues.append({
                'src': src,
                'dest': dest,
                'src_port': src_port,
                'dest_port': dest_port,
                'issue': issue,
                'msg': f"Port doesn't need to be specified for {node_class} on\
 edge {src} -> {dest}."
            })

    # Return fixable issues and errors
    return fixable_issues, errors

def check_template_edges(
    graph: dict
) -> Union[Optional[List[str]], Optional[List[str]]]:
    """Checks the tempalte graph edges and finds any errors and/or issues

    Args:
        graph (dict): Template graph

    Returns:
        Union[Optional[List[str]], Optional[List[str]]]: Fixable issues
                                                        and errors.
    """

    # Lists for fixable issues and errors
    fixable_issues, errors = [], []

    # Iterate through all graph edges
    for src, dest in graph.edges():
        # Unpack edge
        src_node = graph.nodes[src]
        dest_node = graph.nodes[dest]

        # No edges leading out of vacuum
        if src_node['class'] == 'ChemputerVacuum':
            fixable_issues.append({
                'src': src,
                'dest': dest,
                'issue': SWITCH_TO_IN_EDGE,
                'msg': 'out edge not allowed on ChemputerVacuum.',
            })

        # No edges leading into inert gas flask
        if (dest_node['class'] == 'ChemputerFlask'
                and dest_node['chemical'].lower() in INERT_GAS_SYNONYMS):
            fixable_issues.append({
                'src': src,
                'dest': dest,
                'issue': SWITCH_TO_OUT_EDGE,
                'msg': f'in edge not allowed on inert gas flask ({dest}).',
            })

    # Return fixable issues and errors
    return fixable_issues, errors

def get_n_available_backbone_valve_ports(graph: dict) -> int:
    """Get the total number of available ports on backbone valves

    Args:
        graph (dict): Graph to search

    Returns:
        int: Total number of available ports
    """

    # Get all backbone ports
    backbone_valves = get_backbone(graph)

    # Counter for total available ports
    total_available_ports = 0

    # Iterate through all valves
    for valve in backbone_valves:
        used_ports = []
        # Check in edges
        for _, valve, data in graph.in_edges(valve, data=True):
            _, valve_port = data['port']
            if int(valve_port) >= 0:
                used_ports.append(valve_port)

        # Check out edges
        for valve, _, data in graph.out_edges(valve, data=True):
            valve_port, _ = data['port']
            if int(valve_port) >= 0:
                used_ports.append(valve_port)

        # Get all available ports
        available_ports = 6 - len(set(used_ports))

        # Increment counter
        total_available_ports += available_ports

    # return total available ports
    return total_available_ports

def check_flasks(
    reagents_spec: dict,
    buffer_flask_spec: dict,
    cartridge_spec: dict,
    graph: dict
) -> Union[Optional[List[str]], Optional[List[str]]]:
    """Checks all flasks in the graph and finds any issues and/or errors

    Args:
        reagents_spec (dict): Reagent flask specification
        buffer_flask_spec (dict): Buffer flask specification
        cartridge_spec (dict): Cartridge specification
        graph (dict): Graph to check

    Returns:
        Union[Optional[List[str]], Optional[List[str]]]: Fixable issues
                                                        and errors.
    """

    # Lists for fixable issues and errors
    fixable_issues, errors = [], []
    pre_existing_flasks = get_pre_existing_flasks(graph)

    if buffer_flask_spec:
        # Get the total number of buffer flasks required
        n_buffer_flasks_required = max(
            buffer_flask_spec,
            key=lambda item: item['n_required']
        )['n_required']

    # No buffer flask specification given
    else:
        # Default number of buffer flasks required to 0
        n_buffer_flasks_required = 0

    # Find which flasks can be reused and which can be removed.
    flasks_popped = 0
    flasks_used = 0
    buffer_flasks_popped = 0
    buffer_flasks_used = 0
    cartridges_popped = 0

    for chemical, _ in pre_existing_flasks.items():
        if chemical:
            if chemical not in reagents_spec:
                flasks_popped += 1
            else:
                flasks_used += 1
        else:
            if buffer_flasks_used < n_buffer_flasks_required:
                buffer_flasks_used += 1
            else:
                buffer_flasks_popped += 1

    # Find which cartridges can be reused and which can be removed.
    cartridge_chemicals = [
        cartridge['chemical'] for cartridge in cartridge_spec]
    cartridges_used, cartridges_popped = 0, 0

    for chemical, _ in get_pre_existing_cartridges(graph).items():
        if chemical not in cartridge_chemicals:
            cartridges_popped += 1
        else:
            cartridges_used += 1

    # Check enough ports available for flasks
    n_available_ports = (
        get_n_available_backbone_valve_ports(graph)
        + flasks_popped
        + buffer_flasks_popped
        + cartridges_popped
    )
    n_reagent_flasks_required = len(reagents_spec) - flasks_used

    n_buffer_flasks_required = n_buffer_flasks_required - buffer_flasks_used

    total_n_ports_required = (
        n_reagent_flasks_required
        + n_buffer_flasks_required
        + (2 * (len(cartridge_spec) - cartridges_used))
    )

    # Total number of ports needed exceeds number that is available
    if total_n_ports_required > n_available_ports:
        # Log error
        fixable_issues.append({
            'issue': NOT_ENOUGH_SPARE_PORTS,
            'msg': f'{n_reagent_flasks_required} reagent flasks required,\
 {len(cartridge_spec)} cartridges and {n_buffer_flasks_required} empty buffer\
 flasks required but only {n_available_ports} spare ports present in graph.',
            'extra_ports': total_n_ports_required - n_available_ports
        })

    # Return fixable issues and errors
    return fixable_issues, errors

def check_cartridges(
    cartridge_spec: dict,
    graph: dict
) -> Union[Optional[List[str]], Optional[List[str]]]:
    """Checks the cartridge specification and finds any issues and/or errors
    Doesn't seem to be necessary.

    Args:
        cartridge_spec (dict): Cartridge specification
        graph (dict): graph to check

    Returns:
        Union[Optional[List[str]], Optional[List[str]]]: Fixable issues
                                                        and errors.
    """

    # NYI apparently
    fixable_issues, errors = [], []
    return fixable_issues, errors

def check_vessel_spec(
    vessel_spec: dict,
    graph: dict
) -> Union[Optional[List[str]], Optional[List[str]]]:
    """Checks the vessel specification and finds any issues and/or errors

    Args:
        vessel_spec (dict): Vessel specification
        graph (dict): Graph to check

    Returns:
        Union[Optional[List[str]], Optional[List[str]]]: Fixable errors
                                                        and errors
    """

    # Lists for fixable issues and errors
    fixable_issues, errors = [], []

    # Get al lavailable vessels from the graph
    available_vessels = [
        node for node in graph
        if graph.nodes[node]['class'] in [
            CHEMPUTER_SEPARATOR,
            CHEMPUTER_REACTOR,
            CHEMPUTER_FILTER,
            IKA_RV_10
        ]
    ]

    # Create a type mapping of vessel types to classes
    type_mapping = {
        'filter': CHEMPUTER_FILTER,
        'reactor': CHEMPUTER_REACTOR,
        'separator': CHEMPUTER_SEPARATOR,
        'rotavap': IKA_RV_10,
    }

    # Create empty vessel map
    vessel_map = {}

    # Iterate through the vessel spec for component types and IDs
    for component_id, component_type in vessel_spec['types']:
        # Component is present in mapping
        if component_type in type_mapping:
            found_type = False

            # Iterate through total number of available vessels
            for i in range(len(available_vessels)):
                # Get class of the node from the graph
                node_class = graph.nodes[available_vessels[i]]['class']

                # Node class matches that in the type mapping for the component
                if node_class == type_mapping[component_type]:
                    # Add to the vessel mapping
                    found_type = True
                    vessel_map[component_id] = available_vessels[i]

                    # Remove found vessels from available vessel list
                    available_vessels.pop(i)
                    break

            # Cannot find vessel type, log error
            if not found_type:
                errors.append({
                    'error': MISSING_COMPONENT_TYPE_ERROR,
                    'msg': f"Couldn't find {component_type} in graph."
                })

    # Iterate through all temperatures and vessels in specification
    for vessel, temps in vessel_spec['temps'].items():
        # Temperatures are present
        if temps:

            max_temp_required = max(temps, key=lambda temp: temp.temp).temp
            min_temp_required = min(temps, key=lambda temp: temp.temp).temp
            active_cooling_required = False

            # Active cooling required if any temp is lower than previous temp
            # and active=True on step, or if temp is lower than RT.
            for i, temp in enumerate(temps):
                if temp.temp < 18:
                    active_cooling_required = True
                    break

                elif i > 0 and temp.temp < temps[i - 1].temp and temp.active:
                    active_cooling_required = True
                    break

            # Check if chiller is attached to vessel if active cooling required
            adding_chiller_to = []
            if active_cooling_required:
                for _, data in undirected_neighbors(graph, vessel, data=True):
                    if data['class'] in CHILLER_CLASSES:
                        break
                else:
                    fixable_issues.append({
                        'issue': ADD_CHILLER_TO_REACTOR,
                        'msg': 'Reactor requires active cooling so need to add\
 chiller',
                        'reactor': vessel,
                    })
                    adding_chiller_to.append(vessel)

            if max_temp_required <= 25 and min_temp_required >= 18:
                continue

            # Deal with temperatures in range
            else:
                # Vessel is present in vessel mapping
                if vessel in vessel_map:
                    # Get the temperature range for the vessel
                    temp_range = get_vessel_temp_range(
                        vessel_map[vessel], graph
                    )

                    # Temperature not within range, log error
                    if not temp_range:
                        errors.append({
                            'error': MISSING_HEATER_OR_CHILLER_ERROR,
                            'msg': f"Can't find heater/chiller attached to\
 {vessel_map[vessel]}."
                        })

                    # Temperature is in range
                    else:
                        # Get the possible temepratures for the vessel
                        min_temp_possible, max_temp_possible = temp_range

                        # Required minimum temperature below that which
                        # is possible for the vessel, log error
                        if min_temp_required < min_temp_possible:
                            if vessel not in adding_chiller_to:
                                fixable_issues.append({
                                    'issue': ADD_CHILLER_TO_REACTOR,
                                    'msg': f'Reactor needs to go to\
 {min_temp_required} so adding chiller.',
                                    'reactor': vessel,
                                })
                        if max_temp_required > max_temp_possible:
                            errors.append({
                                'error': CANNOT_REACH_TARGET_TEMP_ERROR,
                                'msg': f'{vessel_map[vessel]} cannot go to\
 {max_temp_required} °C as required. Max possible temp: {max_temp_possible} °C'
                            })

    # Rteturn fixable issues and errors
    return fixable_issues, errors

def get_vessel_temp_range(node: dict, graph: dict) -> Tuple[float, float]:
    """Gets the temperature range of a given vessel from the graph

    Args:
        node (dict): Vessel node
        graph (dict): Graph to check

    Returns:
        Tuple[float, float]: Temperature range of vessel
    """

    # Rotavap node
    if graph.nodes[node]['class'] == IKA_RV_10:
        return HEATER_CHILLER_TEMP_RANGES[IKA_RV_10]

    # Iterate through neighbouring nodes of given node
    for neighbor in undirected_neighbors(graph, node):
        # Get the class of the neighbor
        neighbor_class = graph.nodes[neighbor]['class']

        # Class has a temperature range, return
        if neighbor_class in HEATER_CHILLER_TEMP_RANGES:
            return HEATER_CHILLER_TEMP_RANGES[neighbor_class]

    # No temperature range required for node
    return None
