"""
.. module:: utils.execution
    :platforms: Unix, Windows
    :synopsis: Utility functions for use within the platform Executor

"""

from typing import Tuple, Dict, Optional, List, Union
from networkx import MultiDiGraph, NetworkXNoPath
from networkx.algorithms import shortest_path_length, all_simple_paths
from xdl.utils.graph import undirected_neighbors
from xdl.constants import INERT_GAS_SYNONYMS, AIR
from xdl.errors import XDLError, XDLGraphError
from ..constants import (
    SOLID_DISPENSER_CLASSES,
    VACUUM_CLASSES,
    CHEMPUTER_FLASK,
    CHEMPUTER_FILTER,
    CHEMPUTER_REACTOR,
    CHEMPUTER_SEPARATOR,
    CHEMPUTER_PUMP,
    CHEMPUTER_WASTE,
    CHEMPUTER_VALVE,
    CHEMPUTER_CARTRIDGE,
    STIRRER_CLASSES,
    HEATER_CLASSES,
    CHILLER_CLASSES,
    FILTER_CLASSES,
    REACTOR_CLASSES,
    ROTAVAP_CLASSES,
    SEPARATOR_CLASSES,
    FLASK_CLASSES,
    R300_ROTOVAP,
    HEATER_MAX_TEMP,
    CHILLER_MAX_TEMP,
    CHILLER_MIN_TEMP,
    INTERNAL_TEMP_PROBE,
    VALID_TEMPERATURE_SENSORS,
    COMMANDUINO_DEVICE,
    BUBBLE_SENSOR,
    RTD_SENSOR,
    PNEUMATIC_CONTROLLER
)
from .errors import XDLInvalidTempSensorError
from chempiler import Chempiler
import ChemputerAPI
import commanduinolabware

def get_modular_motors(graph: MultiDiGraph) -> Optional[Dict[str, str]]:
    """Gets modular wheel and modular syringe driver motor names from graph.

    Args:
        graph (MultiDiGraph): graph to check.

    Returns:
        Dict[str, str]: modular motors and their device / motor names.
    """

    motors = {}

    for node, data in graph.nodes(data=True):
        if data['class'] == COMMANDUINO_DEVICE:
            if data['name'] in ['wheel', 'modular_wheel']:
                motors['modular_wheel'] = data['motor_name']
                motors['modular_wheel_increments'] = data['increments']
                motors['device_name'] = data['name']
            elif data['name'] in ['syringe', 'modular_syringe']:
                if 'xy_motor' in data:
                    motors['xy_motor'] = data['xy_motor']
                    motors['xy_step_distance'] = data['xy_step_distance']
                if 'z_motor' in data:
                    motors['z_motor'] = data['z_motor']
                    motors['z_step_distance'] = data['z_step_distance']
                if 'device_name' not in motors:
                    motors['device_name'] = data['name']

    return motors

def get_commanduino_graph_cfg(graph: MultiDiGraph) -> Optional[Dict[str, str]]:
    """Checks graph for CommanduinoLabware motor config.

    Args:
        graph (MultiDiGraph): graph to check

    Returns:
        Optional[Dict[str, str]]: commanduino cfg dict
    """
    for node, data in graph.nodes(data=True):
        if data['class'] == COMMANDUINO_DEVICE:
            if 'obj' in data:
                return data['obj']
    return None

def get_mw_positions(graph: MultiDiGraph) -> int:
    """Gets number of vial positions in modular wheel from graph.

    Args:
        graph (MultiDiGraph): graph to check.

    Returns:
        int: number of vial positions in wheel.
    """
    for node, data in graph.nodes(data=True):
        if data['class'] == COMMANDUINO_DEVICE:
            if data['name'] in ['wheel', 'modular_wheel']:
                return data['n_positions']

def get_unused_valve_port(
        graph: MultiDiGraph, valve_node: str) -> Optional[int]:
    """Gets the unused ports on a given valve

    Args:
        graph (MultiDiGraph): Graph to check
        valve_node (str): Valve to check

    Returns:
        Optional[int]: Unused port, none if not found
    """

    used_ports = []
    # Get connected valve positions (In edges).
    for _, _, edge_data in graph.in_edges(valve_node, data=True):
        if 'port' in edge_data:
            used_ports.append(str(edge_data['port'][1]))

    # Get connected valve positions (Out edges).
    for _, _, edge_data in graph.out_edges(valve_node, data=True):
        if 'port' in edge_data:
            used_ports.append(str(edge_data['port'][0]))

    # Return first found unconnected valve positions.
    for i in range(0, 6):  # Possible valve ports are 0, 1, 2, 3, 4, 5.
        if str(i) not in used_ports:
            return str(i)

    # None found
    return None

def get_pneumatic_controller(
    graph: MultiDiGraph, vessel: str, port: str = None
) -> Tuple[str, int]:
    """Given vessel, return pneumatic controller node that is a direct neighbour
    of the vessel in the graph, with the pneumatic controller port number.

    Args:
        vessel (str): Vessel to find attached pneumatic controller
        graph (MultiDiGraph): Graph containing vessel

    Returns:
        Tuple[str, int]: (pneumatic_controller_node, pneumatic_controller_port)
    """

    controller, controller_port, vessel_port = None, None, None

    for src_node, _, info in graph.in_edges(vessel, data=True):
        if graph.nodes[src_node]['class'] == 'PneumaticController':
            controller = src_node
            controller_port, vessel_port = info['port']

            if port is None:
                return src_node, controller_port

            elif port == vessel_port:
                return src_node, controller_port

    return controller, controller_port

def get_vacuum_configuration(
    graph: MultiDiGraph, vessel: str, port: str = None,
) -> Dict[str, str]:
    """Get node names and ports to fully describe vacuum setup as follows:
    vessel <-> ChemputerValve -> ChemputerVacuum <-(Optional vacuum device)

    Args:
        graph (MultiDiGraph): Graph
        vessel (str): Vessel to get vacuum configuration.

    Returns:
        Dict[str, str]: Dictionary containing node names and ports:
            {
                valve: ,  # Valve connecting vessel and vacuum
                source: ,  # ChemputerVacuum attached to valve
                device: ,  # Optional CVC3000 vacuum device attached to source.
                valve_unused_port: ,  # Unused port on valve.
                valve_inert_gas_port: ,  # Port on valve connected to inert gas.
            }
    """
    valve = source = device = valve_unused_port = valve_inert_gas = None
    pneumatic_controller, pneumatic_controller_port = get_pneumatic_controller(
        graph, vessel, port)
    if pneumatic_controller:
        return {
            'valve': valve,
            'source': source,
            'device': device,
            'valve_unused_port': valve_unused_port,
            'valve_inert_gas': valve_inert_gas,
            'pneumatic_controller': pneumatic_controller,
            'pneumatic_controller_port': pneumatic_controller_port,
        }

    for neighbor, neighbor_data in undirected_neighbors(
            graph, vessel, data=True):

        # Find valve
        if not valve and neighbor_data['class'] == 'ChemputerValve':

            for valve_neighbor, valve_neighbor_data in undirected_neighbors(
                    graph, neighbor, data=True):

                # Find vacuum
                if valve_neighbor_data['class'] == 'ChemputerVacuum':

                    # Only assign valve as attached valve connected to vacuum
                    valve = neighbor
                    source = valve_neighbor

                    # Find vacuum device if there.
                    for source_neighbor, source_neighbor_data in\
                            undirected_neighbors(
                                graph, source, data=True):
                        if source_neighbor_data['class'] in VACUUM_CLASSES:
                            device = source_neighbor

                # Find inert gas
                elif valve_neighbor_data['class'] == 'ChemputerFlask':
                    if valve_neighbor_data['chemical'] in INERT_GAS_SYNONYMS:
                        valve_inert_gas = valve_neighbor

                # Find pneumatic controller
                elif valve_neighbor_data['class'] == PNEUMATIC_CONTROLLER:
                    pneumatic_controller, pneumatic_controller_port =\
                        get_pneumatic_controller(graph, neighbor)
                    valve = neighbor

    if valve:
        valve_unused_port = get_unused_valve_port(graph, valve)

    return {
        'valve': valve,
        'source': source,
        'device': device,
        'valve_unused_port': valve_unused_port,
        'valve_inert_gas': valve_inert_gas,
        'pneumatic_controller': pneumatic_controller,
        'pneumatic_controller_port': pneumatic_controller_port,
    }

def get_buffer_flask(
        graph: MultiDiGraph, vessel: str, return_single=True) -> str:
    """Get buffer flask closest to given vessel.

    Args:
        vessel (str): Node name in graph.

    Returns:
        str: Node name of buffer flask (unused reactor) nearest vessel.
    """
    # Get all reactor IDs
    flasks = [
        flask
        for flask, data in graph_flasks(graph, data=True)
        if not data['chemical']
    ]

    # From remaining reactor IDs, return nearest to vessel.
    if flasks:
        if len(flasks) == 1:
            return flasks[0] if return_single else [flasks[0]]

        # More than one flask
        else:
            shortest_paths = []
            for flask in flasks:
                shortest_paths.append((
                    flask,
                    shortest_path_length(graph, source=vessel, target=flask)
                ))

            if return_single:
                return sorted(shortest_paths, key=lambda x: x[1])[0][0]

            else:
                return [
                    item[0]
                    for item in sorted(shortest_paths, key=lambda x: x[1])
                ]

    return None if return_single else [None, None]

def get_stirring_controller(graph: MultiDiGraph, node: str) -> str:
    """Get stirring controller associated with given node. This will either
    be the node itself or a neighboring node.

    Args:
        graph (MultiDiGraph): Graph to get stirring controller from.
        node (str): Node to get stirring controller associated with it.
            For example this can be a reactor or flask.
    """

    # Check if node is a stirring controller
    node_class = graph.nodes[node]['class']
    if node_class in STIRRER_CLASSES + HEATER_CLASSES + ROTAVAP_CLASSES:
        return node

    # Find neighboring stirring controller. Only check for rotavap for node not
    # neighbors as rotavap can only provide stirring for itself.
    else:
        for neighbor, data in undirected_neighbors(graph, node, data=True):
            if data['class'] in STIRRER_CLASSES + HEATER_CLASSES:
                return neighbor

    return None

def get_pressure_controller(graph: MultiDiGraph, node: str) -> str:
    """Get pressure controller associated with given node. This will either
    be the node itself or a neighboring node.

    Args:
        graph (MultiDiGraph): Graph to get pressure controller from.
        node (str): Node to get pressure controller associated with it.
            For example this can be a reactor or flask.
    """

    # Check if node is a pressure controller
    node_class = graph.nodes[node]['class']
    if (node_class in VACUUM_CLASSES
            or node_class == R300_ROTOVAP):
        return node

    # Find neighboring vacuum. Only check for rotavap for node not
    # neighbors as rotavap can only provide vacuum for itself.
    else:
        for neighbor, data in undirected_neighbors(graph, node, data=True):
            if data['class'] in VACUUM_CLASSES:
                return neighbor

    return None

def get_temperature_controller(
        graph: MultiDiGraph, node: str, temp: float = 25) -> str:
    """Get temperature controller associated with given node. This will either
    be the node itself or a neighboring node.

    Args:
        graph (MultiDiGraph): Graph to get temperature controller from.
        node (str): Node to get temperature controller associated with it.
            For example this can be a reactor or flask.
    """

    # Check if node is a temperature controller
    node_class = graph.nodes[node]['class']
    if node_class in HEATER_CLASSES + CHILLER_CLASSES + ROTAVAP_CLASSES:
        return node

    # Find neighboring heater or chiller. Only check for rotavap for node not
    # neighbors as rotavap can only heat itself.
    else:
        heater, chiller = None, None
        for neighbor, data in undirected_neighbors(graph, node, data=True):
            if data['class'] in HEATER_CLASSES:
                heater = neighbor
            elif data['class'] in CHILLER_CLASSES:
                chiller = neighbor

        # Try and use chiller
        if chiller and CHILLER_MIN_TEMP <= temp <= CHILLER_MAX_TEMP:
            return chiller

        # Try and use heater
        elif heater and 18 <= temp <= HEATER_MAX_TEMP:
            return heater

    return None

def get_temperature_controller_sensor(
        graph: MultiDiGraph, temperature_controller: str) -> str:
    """Get sensor type to use for reading temperature. 'internal' or 'external'.

    Args:
        graph (MultiDiGraph): Graph object with all availalbe nodes in the
                              system.
        temperature_controller (str): Name of the temperature controller node.

    Exceptions:
        raises XDLGraphError when there is no valid definition of a temperature
            probe.
    """

    node = graph.nodes[temperature_controller]
    if node['class'] in ROTAVAP_CLASSES:
        return INTERNAL_TEMP_PROBE
    sensor = node.get('temp_sensor', False)
    # Default to 'external' for hotplates to align with SL1 behaviour, and cause
    # clear error rather than hard-to-trace failure of synthesis. This is only
    # relevant to old graphs that have not been loaded and saved in ChemIDE
    # since the `temp_sensor` prop was added.
    if sensor not in VALID_TEMPERATURE_SENSORS:
        if not sensor:
            msg = ("No temperature probe has been defined for "
                   f"'{temperature_controller}' in the graph.")
        else:
            # Turn the dictionary of valid sensors into a neat human-readable
            # string.
            valid_sensors = str([k for k in VALID_TEMPERATURE_SENSORS.keys()])
            valid_sensors = " and".join(valid_sensors[1:-1].rsplit(',', 1))
            msg = ("An invalid value for the temperature probe of "
                   f"'{temperature_controller}' has been given in the "
                   f"graph. Valid values are {valid_sensors}. "
                   f"Received '{sensor}' instead.")
        raise XDLGraphError(msg)
    return sensor

def convert_sensor_type_to_pylabware2_code(sensor: str) -> int:
    """Converts the sensor type to the sensor code used in PyLabware2.

    Args:
        sensor (str): Temperature sensor. Currently supported types are
            'internal' (PyLabware2 code '0') and 'external'
            (PyLabware2 code '1').

    Exceptions:
        raises XDLExecutionError when there is no valid definition of a
            temperature sensor.
    """

    sensor_code = VALID_TEMPERATURE_SENSORS.get(sensor, None)
    if sensor_code is None:
        raise XDLInvalidTempSensorError(sensor)

    return sensor_code

def get_node_temp_range(graph: MultiDiGraph, node: str) -> Tuple[float, float]:
    """Get minimum / maximum temperature that given node can heat or chill to.
    Assumes node is a heater or a chiller.

    Args:
        graph (MultiDiGraph): Graph to get node information from.
        node (str): Node to find temperature range for.

    Returns:
        Tuple[float, float]: Temperature range node can heat / chill to in
        ``(min_temp, max_temp)`` tuple.
    """
    min_temp, max_temp = None, None
    node_props = graph.nodes[node]

    # Look for min temp given in graph
    if 'min_temp' in node_props and node_props['min_temp'] not in ['', None]:
        min_temp = float(node_props['min_temp'])

    # No min temp in graph so use hardcoded min temp
    else:
        node_class = node_props['class']
        if node_class in CHILLER_CLASSES:
            min_temp = CHILLER_MIN_TEMP
        elif node_class in HEATER_CLASSES:
            min_temp = 18
        elif node_class in ROTAVAP_CLASSES:
            min_temp = 18

    # Look for max temp given in graph
    if 'max_temp' in node_props and node_props['max_temp'] not in ['', None]:
        max_temp = float(node_props['max_temp'])

    # No max temp in graph so use hardcoded max temp
    else:
        node_class = node_props['class']
        if node_class in CHILLER_CLASSES:
            max_temp = CHILLER_MAX_TEMP
        elif node_class in HEATER_CLASSES:
            max_temp = HEATER_MAX_TEMP
        elif node_class in ROTAVAP_CLASSES:
            max_temp = HEATER_MAX_TEMP

    return min_temp, max_temp


def get_heater_chiller(graph: MultiDiGraph, node: str) -> Tuple[str, str]:
    """Gets the Heater and Chiller nodes from the graph

    Args:
        graph (MultiDiGraph): Graph to check
        node (str): Node to check

    Returns:
        Tuple[str, str]: Heater and Chiller
    """

    heater, chiller = None, None

    # Get all neighbors of the node
    neighbors = undirected_neighbors(graph, node)

    # Iterate through each neighbor
    for neighbor in neighbors:
        # Found a heater
        if graph.nodes[neighbor]['class'] in HEATER_CLASSES:
            heater = neighbor

        # Found a chiller
        elif graph.nodes[neighbor]['class'] in CHILLER_CLASSES:
            chiller = neighbor

    return heater, chiller

def get_chiller(graph: MultiDiGraph, vessel: str) -> str:
    """Gets chiller attached to given vessel.

    Args:
        graph (MultiDiGraph): Graph to check
        node (str): Node to check

    Returns:
        Tuple[str, str]: Heater and Chiller
    """

    chiller = None

    # Get all neighbors of the node
    neighbors = undirected_neighbors(graph, vessel)

    # Iterate through each neighbor
    for neighbor in neighbors:

        # Found chiller
        if graph.nodes[neighbor]['class'] in CHILLER_CLASSES:
            chiller = neighbor

    return chiller

def get_heater(graph: MultiDiGraph, vessel: str) -> str:
    """Gets heater attached to given vessel.

    Args:
        graph (MultiDiGraph): Graph to check
        node (str): Node to check

    Returns:
        str: Heater node name
    """

    heater = None

    # Get all neighbors of the node
    neighbors = undirected_neighbors(graph, vessel)

    # Iterate through each neighbor
    for neighbor in neighbors:

        # Found heater
        if graph.nodes[neighbor]['class'] in HEATER_CLASSES:
            heater = neighbor

    return heater

def get_solid_dispenser(graph: MultiDiGraph, vessel: str) -> str:
    """Finds a solid dispenser node attached to a vessel

    Args:
        graph (MultiDiGraph): Graph to search through
        vessel (str): Vessel attached to solid dispenser

    Returns:
        str: Dispesner Name from the graph
    """

    dispenser = None

    # Get all neighbours of the node
    neighbors = undirected_neighbors(graph, vessel)

    # Iterate trhough each neighbor
    for neighbor in neighbors:
        # Found a dispenser, set it and break out
        if graph.nodes[neighbor]['class'] in SOLID_DISPENSER_CLASSES:
            dispenser = neighbor
            break

    return dispenser

def get_nearest_node(
    graph: MultiDiGraph,
    src: str,
    target_vessel_class: str,
    src_port: Optional[str] = None,
) -> str:
    """Gets the nearest node from the src of target vessel class

    Args:
        graph (MultiDiGraph): Graph to check
        src (str): Node to check
        target_vessel_class (str): Node class to search for
        src_port (Optional[str]): Optional src port to use when calculating
            shortest paths.

    Raises:
        NetworkXNoPath: Cannot find a path between nodes

    Returns:
        str: Nearest node of vessel class
    """

    # Make graph undirected so actual closest waste vessels are found, not
    # closest in liquid flow path. As long as vessels are all attached to a
    # valve which is attached to a waste vessel this should be fine.
    target_vessels = [
        node for node in graph.nodes()
        if (graph.nodes[node]['class']
            == target_vessel_class)
    ]

    # Make shortest length huge on purpose
    shortest_path_found = 100000
    closest_target_vessel = None

    # Go through each target vessel
    for target_vessel in target_vessels:
        try:
            # Port not given, just use shortest path length
            if src_port is None:
                # Calculate shortest path
                shortest_path_to_target_vessel = shortest_path_length(
                    graph, source=src, target=target_vessel
                )

            # Src port specified, filter out paths with invalid ports before
            # looking for shortest path length.
            else:
                # Get all paths
                paths = list(all_simple_paths(
                    graph, source=src, target=target_vessel))

                # Get valid first edges in path
                valid_first_edges = []
                for edge_src, edge_dest, data in graph.edges(data=True):
                    if edge_src == src and data['port'][0] == src_port:
                        valid_first_edges.append((edge_src, edge_dest))

                # Filter out paths with invalid src ports
                for i in reversed(range(len(paths))):
                    path = paths[i]
                    if (path[0], path[1]) not in valid_first_edges:
                        paths.pop(i)

                # Get shortest path with valid ports
                if paths:
                    shortest_path_to_target_vessel = min(
                        [len(path) for path in paths])

            # Shortest so far, set target vessel to node
            if shortest_path_to_target_vessel < shortest_path_found:
                shortest_path_found = shortest_path_to_target_vessel
                closest_target_vessel = target_vessel

        except NetworkXNoPath:
            pass

    # Return node with the shortest path found
    return closest_target_vessel

def get_vessel_stirrer(graph: MultiDiGraph, vessel: str) -> Optional[str]:
    """Get any stirrer attached to given vessel
    Heaters can be stirrers in the case of stirrer hot plates

    Args:
        graph (MultiDiGraph): Graph to search
        vessel (str): Vessel to check

    Returns:
        Optional[str]: Stirrer node, none if not found
    """
    # Check whether the vessel is a rotavap which has
    # the stirring ability integrated.
    if graph.nodes[vessel]['class'] in ROTAVAP_CLASSES:
        return vessel
    # Check whether the vessel has an external stirrer attached.
    else:
        stirrer_neighbors, heater_neighbors = [], []
        stirrer = None
        # Iterate through each neighbor node of the vessel
        for neighbor, data in undirected_neighbors(graph, vessel, data=True):
            # Found a stirrer
            if data['class'] in STIRRER_CLASSES:
                stirrer_neighbors.append(neighbor)

            # Found a heater
            elif data['class'] in HEATER_CLASSES:
                heater_neighbors.append(neighbor)

        # Return first stirrer found
        if stirrer_neighbors:
            stirrer = stirrer_neighbors[0]

        # Return first heater/stirrer found
        elif heater_neighbors:
            stirrer = heater_neighbors[0]

        return stirrer

def get_reagent_vessel(graph: MultiDiGraph, reagent: str) -> Optional[str]:
    """Get vessel containing given reagent.

    Args:
        reagent (str): Name of reagent to find vessel for.

    Returns:
        str: ID of vessel containing given reagent.
    """

    for node, data in graph.nodes(data=True):
        if data['class'] == CHEMPUTER_FLASK:
            if data['chemical'] == reagent:
                return node

    return None

def get_backbone(graph: MultiDiGraph, ordered: bool = False) -> List[str]:
    """Get list of all valves that have a pump attached.

    Args:
        graph (MultiDiGraph): Graph to check
        ordered (bool): Order the backbone or not

    Raises:
        XDLError: No backbone found

    Returns:
        List[str]: List of all backbone valves
    """

    backbone = []

    # Iterate through all valves
    for valve in graph_valves(graph):
        has_pump = False

        # Determine if valve has a pump attached
        for _, neighbor_data in undirected_neighbors(graph, valve, data=True):
            if neighbor_data['class'] == CHEMPUTER_PUMP:
                has_pump = True
                break

        # Has a pump, should be in the backbone
        if has_pump:
            backbone.append(valve)

    # Order not important just return
    if not ordered:
        return backbone

    # Order from start to finish
    else:
        # Get the valves at the end of the backbone
        backbone_end_valves = get_backbone_end_valves(graph, backbone)

        # Two valves at the end of the backbone
        if len(backbone_end_valves) == 2:
            start = backbone_end_valves[0]
            end = backbone_end_valves[1]

            # Swap valves
            if graph.nodes[start]['x'] > graph.nodes[end]['x']:
                start = backbone_end_valves[1]
                end = backbone_end_valves[0]

            node = start
            ordered_backbone = [start]

            # Start shifting all valves in order
            while node != end:
                for neighbor in undirected_neighbors(graph, node):
                    if (neighbor in backbone
                            and neighbor not in ordered_backbone):
                        node = neighbor
                        ordered_backbone.append(node)
                        break

            return ordered_backbone

        # Return the valves as only one end
        elif len(backbone_end_valves) == 1:
            return backbone_end_valves

        # No backbone found
        else:
            raise XDLError(
                f'No backbone found.\n\
Backbone end valves: {backbone_end_valves}\n\
Backbone valves: {backbone}.'
            )

def get_backbone_end_valves(
        graph: MultiDiGraph, backbone: List[str]) -> List[str]:
    """Get two valves at each end of backbone.

    Args:
        graph (MultiDiGraph): Graph to search
        backbone (List[str]): List of backbone valves

    Returns:
        List[str]: Valves at each end of the backbone
    """

    backbone_end_valves = []

    if len(backbone) == 1:
        return [backbone[0], backbone[0]]

    # iterate through all backbone valves
    for valve in backbone:
        valve_neighbors = 0

        # Iterate through all neighbors of current valve
        for neighbor, _ in undirected_neighbors(
                graph, valve, data=True):

            # Neighbor is in backbone, increment counter
            if neighbor in backbone:
                valve_neighbors += 1

        # One neighbor, add to end valves
        if valve_neighbors == 1:
            backbone_end_valves.append(valve)

    return backbone_end_valves

def get_waste_vessel(graph: MultiDiGraph, vessel: str) -> str:
    """Get nearest waste vessel to node.

    Args:
        graph (MultiDiGraph): Graph to check
        vessel (str): Vessel to check

    Returns:
        str: Waste vessel
    """

    # Get waste vessel from valve
    waste = get_waste_on_valve(graph, vessel)

    # Can't find on valve, get nearest waste
    if not waste:
        waste = get_nearest_node(graph, vessel, CHEMPUTER_WASTE)

    return waste

def get_waste_on_valve(graph: MultiDiGraph, vessel: str) -> Optional[str]:
    """Get waste vessel connected to backbone valve connected to node. If
    node given is a backbone valve just use that.

    Args:
        graph (MultiDiGraph): Graph to check
        vessel (str): Vessel to check

    Returns:
        Optional[str]: Waste vessel if found, else None
    """

    # Vessel is valve
    if graph.nodes[vessel]['class'] == CHEMPUTER_VALVE:
        return _waste_on_valve(graph, vessel)

    # Vessel is not valve, find connected valve then find waste.
    else:
        for node, data in undirected_neighbors(graph, vessel, data=True):
            if data['class'] == CHEMPUTER_VALVE:
                waste = _waste_on_valve(graph, node)
                if waste:
                    return waste

    return None

def _waste_on_valve(graph: MultiDiGraph, valve: str) -> Optional[str]:
    """Used by get_waste_on_valve to get waste connected to given valve.

    Args:
        graph (MultiDiGraph): Graph to search
        valve (str): Valve to check

    Returns:
        Optional[str]: Waste vessel if found else None
    """

    has_pump = False
    waste = None

    # Iterate through all neighbors of the valve
    for valve_neighbor, valve_neighbor_data in undirected_neighbors(
        graph, valve, data=True
    ):
        # Found a waste vessel
        if valve_neighbor_data['class'] == CHEMPUTER_WASTE:
            waste = valve_neighbor
        elif valve_neighbor_data['class'] == CHEMPUTER_PUMP:
            has_pump = True
        if has_pump and waste:
            return waste

    return None

def get_pump_on_valve(graph: MultiDiGraph, valve: str) -> Optional[str]:
    """Find pump attached to given valve.

    Args:
        graph (MultiDiGraph): Graph to search
        valve (str): Valve to check

    Returns:
        Optional[str]: Pump node name if found else None
    """

    # Iterate through all neighbors of the valve
    for valve_neighbor, valve_neighbor_data in undirected_neighbors(
        graph, valve, data=True
    ):
        # Found pump
        if valve_neighbor_data['class'] == CHEMPUTER_PUMP:
            return valve_neighbor

    return None

def get_flush_tube_vessel(graph: MultiDiGraph, vessel: str) -> Optional[str]:
    """Look for gas vessel to flush tube with after Add steps. Vessel must be on
    the backbone.

    Args:
        graph (MultiDiGraph): Graph to check
        vessel (str): Vessel to check

    Returns:
        str: Flask to use for flushing tube.
            Preference is nitrogen > air > None.
    """
    inert_gas_flasks, air_flasks = [], []

    # Iterate through all backbone valves
    for valve in get_backbone(graph):
        # Find all vessels that contain inert gas or air
        for neighbor, data in undirected_neighbors(graph, valve, data=True):
            if data['class'] == CHEMPUTER_FLASK:
                if data['chemical'].lower() in INERT_GAS_SYNONYMS:
                    inert_gas_flasks.append(neighbor)

                elif data['chemical'].lower() == AIR:
                    air_flasks.append(neighbor)

    # Inert gas flasks were found
    if inert_gas_flasks:
        # Only one, return
        if len(inert_gas_flasks) == 1:
            return inert_gas_flasks[0]

        # More than one, get the closest one
        else:
            path_lengths = []
            for inert_gas_flask in inert_gas_flasks:
                path_lengths.append((
                    inert_gas_flask,
                    shortest_path_length(
                        graph, inert_gas_flask, vessel
                    )
                ))
            return sorted(path_lengths, key=lambda x: x[1])[0][0]

    # Flasks contianing air found
    elif air_flasks:
        # Only one, return that
        if len(air_flasks) == 1:
            return air_flasks[0]

        # More than one, return the closest one
        else:
            path_lengths = []
            for air_flask in air_flasks:
                path_lengths.append((
                    air_flask,
                    shortest_path_length(
                        graph, air_flask, vessel
                    )
                ))
            return sorted(air_flasks, key=lambda x: x[1])[0][0]

    return None

def get_rotavap_collection_flask_volume(
        graph: MultiDiGraph, rotavap: str) -> float:
    """Return volume of rotavap collection flask.

    Args:
        graph (MultiDiGraph): Graph containing node ``rotavap``.
        rotavap (str): Node name of rotavap.

    Returns:
        float: Volume of collection flask. ``None`` if collection flask volume
            not given in graph.
    """
    rotavap_node = graph.nodes[rotavap]
    if 'collection_flask_volume' in rotavap_node:
        return rotavap_node[
            'collection_flask_volume'
        ]
    return None

def get_chempiler(graph: MultiDiGraph, device_modules: List = []) -> Chempiler:
    """Creates a Chempiler object

    Args:
        graph (MultiDiGraph): Chempiler graph
        device_modules (List, optional): Device module to load into
                                        the chempiler. Defaults to [].

    Returns:
        Chempiler: Chempiler object
    """

    return Chempiler(
        experiment_code="null",
        output_dir='',
        simulation=True,
        device_modules=[ChemputerAPI, commanduinolabware] + device_modules,
        graph_file=graph
    )

def get_vessel_type(graph: MultiDiGraph, vessel: str) -> Optional[str]:
    """Gets the type of vessel from the graph

    Args:
        graph (MultiDiGraph): Graph to check
        vessel (str): Name of the vessel

    Returns:
        Optional[str]: Vessel type, None if not found
    """

    # Get the vessel type
    vessel_class = graph.nodes[vessel]['class']

    # Determine type
    if vessel_class in FILTER_CLASSES:
        return 'filter'
    elif vessel_class in ROTAVAP_CLASSES:
        return 'rotavap'
    elif vessel_class in REACTOR_CLASSES:
        return 'reactor'
    elif vessel_class in SEPARATOR_CLASSES:
        return 'separator'
    elif vessel_class in FLASK_CLASSES:
        return 'flask'

    # Type not found
    return None

def node_in_graph(graph: MultiDiGraph, node: str) -> bool:
    """Determines if a node is present within the graph

    Args:
        graph (MultiDiGraph): Graph to check
        node (str): Node to check for

    Returns:
        bool: Node is present in the graph
    """

    return node in graph.nodes()

def get_cartridge(graph: MultiDiGraph, chemical: str) -> Optional[str]:
    """Get the cartridge from the graph

    Args:
        graph (MultiDiGraph): Graph to check
        chemical (str): Cartridge to check for

    Returns:
        Optional[str]: Cartridge if found, else None
    """

    for cartridge, data in graph_cartridges(graph, data=True):
        if data['chemical'] == chemical:
            return cartridge

    return None

def graph_flasks(graph, data=False) -> str:
    """Generator to iterate through all ChemputerFlasks in graph.

    Args:
        graph (MultiDiGraph): Graph
        data (bool): Give node data in (node, data) tuple. Defaults to False.

    Yields:
        str: Flask from the graph
    """

    for item in graph_iter_class(graph, CHEMPUTER_FLASK, data=data):
        yield item

def graph_cartridges(graph: MultiDiGraph, data: bool = False) -> str:
    """Generator to iterate through all ChemputerCartridges in graph.

    Args:
        graph (MultiDiGraph): Graph
        data (bool): Give node data in (node, data) tuple. Defaults to False.

    Yields:
        str: Cartridge from the graph
    """

    for item in graph_iter_class(graph, CHEMPUTER_CARTRIDGE, data=data):
        yield item

def graph_valves(graph: MultiDiGraph, data: bool = False) -> str:
    """Generator to iterate through all ChemputerValves in graph.

    Args:
        graph (MultiDiGraph): Graph
        data (bool): Give node data in (node, data) tuple. Defaults to False.

    Yields:
        str: Valve from the graph
    """

    for item in graph_iter_class(graph, CHEMPUTER_VALVE, data=data):
        yield item

def graph_filters(graph: MultiDiGraph, data: bool = False) -> str:
    """Generator to iterate through all ChemputerFilters in graph.

    Args:
        graph (MultiDiGraph): Graph
        data (bool): Give node data in (node, data) tuple. Defaults to False.

    Yields:
        str: Valve from the graph
    """

    for item in graph_iter_class(graph, CHEMPUTER_FILTER, data=data):
        yield item

def graph_reactors(graph: Dict, data: bool = False) -> str:
    """Generator to iterate through all ChemputerReactors in graph.

    Args:
        graph (MultiDiGraph): Graph
        data (bool): Give node data in (node, data) tuple. Defaults to False.

    Yields:
        str: Valve from the graph
    """

    for item in graph_iter_class(graph, CHEMPUTER_REACTOR, data=data):
        yield item

def graph_separators(graph: Dict, data: bool = False) -> str:
    """Generator to iterate through all ChemputerSeparators in graph.

    Args:
        graph (MultiDiGraph): Graph
        data (bool): Give node data in (node, data) tuple. Defaults to False.

    Yields:
        str: Valve from the graph
    """

    for item in graph_iter_class(graph, CHEMPUTER_SEPARATOR, data=data):
        yield item

def graph_rotavaps(graph: Dict, data: bool = False) -> str:
    """Generator to iterate through all ChemputerSeparators in graph.

    Args:
        graph (MultiDiGraph): Graph
        data (bool): Give node data in (node, data) tuple. Defaults to False.

    Yields:
        str: Valve from the graph
    """

    for item in graph_iter_class(graph, ROTAVAP_CLASSES, data=data):
        yield item

def graph_wastes(graph: Dict, data: bool = False) -> str:
    """Generator to iterate through all ChemputerWastes in graph.

    Args:
        graph (MultiDiGraph): Graph
        data (bool): Give node data in (node, data) tuple. Defaults to False.

    Yields:
        str: Valve from the graph
    """

    for item in graph_iter_class(graph, CHEMPUTER_WASTE, data=data):
        yield item

def graph_iter_class(
    graph: MultiDiGraph, target_class: Union[List, str], data: bool = False
) -> Tuple[str, Dict[str, str]]:
    """Iterates through all classes in the graph

    Args:
        graph (MultiDiGraph): Graph to check
        target_class (Union[List,str]): Class to check for. Can be single class
            or list of classes.
        data (bool, optional): Use graph data or not. Defaults to False.

    Yields:
        Tuple[str, Dict[str, str]]: Node and data, or just Node
    """
    # If single target class given convert to list for uniform behaviour.
    if type(target_class) is str:
        target_class = [target_class]

    # Iterate through nodes looking for nodes with target class.
    for node, node_data in graph.nodes(data=True):
        if node_data['class'] in target_class:
            if data:
                yield node, node_data
            else:
                yield node

def get_aspiration_pump(
        graph: MultiDiGraph, src_vessel: str, src_port: Optional[str] = None
) -> str:
    """ Get the aspiration pump closest to the source vessel.

    Args:
        graph (MultiDiGraph): Graph to look in.
        src_vessel (str): Name of the source vessel.
        src_port (str, optional): Source port on the source vessel.

    Returns:
        str: Name of the aspiration pump.
    """
    # TODO Report an exception in get_nearest_node!
    try:
        aspiration_pump = get_nearest_node(
            graph=graph,
            src=src_vessel,
            src_port=src_port,
            target_vessel_class=CHEMPUTER_PUMP
        )
    except UnboundLocalError:
        aspiration_pump = get_nearest_node(
            graph=graph, src=src_vessel, target_vessel_class=CHEMPUTER_PUMP
        )

    return aspiration_pump

def get_pump_max_volume(
        graph: MultiDiGraph, aspiration_pump: str
) -> float:
    """ Gets the pump's maximum volume from the graph

    Args:
        graph (MultiDiGraph): Graph to look in.
        aspiration_pump (str): Name of the pump node.

    Returns:
        float: Maximum volume of the pump as recorded in graph.
    """

    pump_obj = graph.nodes[aspiration_pump]

    return pump_obj['max_volume']

def get_bubble_sensor(
        graph: MultiDiGraph, pump: str
) -> str:
    """ Gets the bubble sensor attached to the pump.

    Args:
        graph (MultiDiGraph): Graph to look in.
        pump (str): Name of the pump node.

    Returns:
        str: Name of the bubble sensor node.
    """

    bubble_sensor = None

    # Getting all neighbors of the pump
    neighbors = undirected_neighbors(graph, pump)

    # Looking for sensor
    for neighbor in neighbors:
        if graph.nodes[neighbor]['class'] == BUBBLE_SENSOR:
            bubble_sensor = neighbor

    return bubble_sensor

def get_rtd_sensor(graph: MultiDiGraph, vessel: str) -> str:
    """ Gets the rtd sensor attached to the vessel.

    Args:
        graph (MultiDiGraph): Graph to look in.
        vessel (str): Name of the vessel node.

    Returns:
        str: Name of the RTD temperature sensor node.
    """

    rtd_sensor = None

    # Get all neighbors of the node
    neighbors = undirected_neighbors(graph, vessel)
    # Iterate through each neighbor
    for neighbor in neighbors:
        # Find temp sensor
        if graph.nodes[neighbor]['class'] == RTD_SENSOR:
            rtd_sensor = neighbor

    return rtd_sensor
