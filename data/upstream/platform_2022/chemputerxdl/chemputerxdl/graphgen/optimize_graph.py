"""
.. module:: graphgen.optimize_graph
    :platforms: Unix, Windows
    :synopsis: Attemtps to optimize the XDL graph

"""

# Standard
import copy
import random
from typing import List, Dict, Optional, Tuple
from networkx import MultiDiGraph

# Relative
from ..utils.execution import get_backbone
from ..steps import (
    Add,
    WashSolid,
    Separate,
    FilterThrough,
    Recrystallize,
    FlushTubing,
)
from ..constants import DEFAULT_AIR_FLUSH_TUBE_VOLUME

# XDL
from xdl.utils.graph import undirected_neighbors

def cartridge_in_pseudo_flask_name(cartridge_chemical: str) -> str:
    """Placeholder name used for pseudo flask representing the position at which
    the edge to the cartridge in port starts.

    Args:
        cartridge_chemical (str): Cartridge name

    Returns:
        str: Formatted name.
    """

    return f'{cartridge_chemical}-cartridge-in'

def cartridge_out_pseudo_flask_name(cartridge_chemical: str) -> str:
    """Placeholder name used for pseudo flask representing the position at which
    the edge from the cartridge out port ends.

    Args:
        cartridge_chemical (str): Cartridge name

    Returns:
        str: Formatted name.
    """

    return f'{cartridge_chemical}-cartridge-out'

def add_transfer_to_dict(
    transfer_dict: Dict, transfer: str, volume: float
) -> Dict:
    """Adds a transfer to Transfer colelction

    Args:
        transfer_dict (Dict): Transfers collection
        transfer (str): Name of new transfer
        volume (float): Volume of new transfer

    Returns:
        Dict: Updated transfer collection
    """
    if transfer in transfer_dict:
        transfer_dict[transfer] += volume
    else:
        transfer_dict[transfer] = volume

    return transfer_dict

def get_transfers(xdl_obj, graph, flasks, inert_gas_flask=None):
    """Get map of reagent transfer and volume of liquid transferred over whole
    procedure. Return as dict { (from_flask, to_vessel): total_volume... }.

    Args:
        xdl_obj (XDL): XDL object
        flasks (Dict): Flasks to find optimal positions for

    Returns:
        Dict: Optimal transfers
    """

    transfers = {}

    # Iterate through all XDL steps
    for step in xdl_obj.steps:
        # Add step
        if type(step) == Add and step.volume is not None:
            transfer = (flasks[step.reagent], step.vessel)
            volume = step.volume
            add_transfer_to_dict(transfers, transfer, volume)

            if inert_gas_flask:
                inert_gas_transfer = (inert_gas_flask, step.vessel)
                add_transfer_to_dict(transfers, inert_gas_transfer, volume)

        # WashSolid step
        elif type(step) == WashSolid:
            transfer = (flasks[step.solvent], step.vessel)
            volume = step.volume * step.repeats
            add_transfer_to_dict(transfers, transfer, volume)

        elif type(step) == Separate:
            # Solvent transfer
            if step.solvent:
                transfer = (flasks[step.solvent], step.separation_vessel)
                solvent_volume = step.solvent_volume * step.repeats
                add_transfer_to_dict(transfers, transfer, solvent_volume)
            else:
                volume = graph.nodes[step.separation_vessel]['max_volume'] / 3

            # Through cartridge transfer
            if step.through:
                in_transfer = (
                    step.separation_vessel,
                    cartridge_in_pseudo_flask_name(step.through)
                )
                out_transfer = (
                    cartridge_out_pseudo_flask_name(step.through),
                    step.to_vessel
                )
                # Use solvent volume if available, otherwise placeholder volume
                # derived from separator max volume.
                through_volume = volume
                if step.solvent:
                    through_volume = solvent_volume

                add_transfer_to_dict(transfers, in_transfer, through_volume)
                add_transfer_to_dict(transfers, out_transfer, through_volume)

            # Flush tubing
            if inert_gas_flask:
                transfer = (inert_gas_flask, step.to_vessel)
                add_transfer_to_dict(
                    transfers, transfer, DEFAULT_AIR_FLUSH_TUBE_VOLUME)

        # Recrystallise step
        elif type(step) == Recrystallize and step.solvent:
            volume = step.solvent_volume
            add_transfer_to_dict(transfers, transfer, volume)

        # FilterThrough step
        elif type(step) == FilterThrough and step.eluting_solvent:
            # Get cartridge pseudo flask names
            in_cartridge_pseudo_flask = cartridge_in_pseudo_flask_name(
                step.through)

            out_cartridge_pseudo_flask = cartridge_out_pseudo_flask_name(
                step.through)

            # Volume unknown so use third of max volume, arbitrary
            volume = graph.nodes[step.from_vessel]['max_volume'] / 3

            # Eluting solvent to from_vessel
            transfer = (flasks[step.eluting_solvent], step.from_vessel)
            eluting_volume = step.eluting_volume * step.eluting_repeats
            add_transfer_to_dict(transfers, transfer, eluting_volume)

            # Eluting solvent from from_vessel to cartridge_in
            transfer = (step.from_vessel, in_cartridge_pseudo_flask)
            add_transfer_to_dict(transfers, transfer, eluting_volume)

            # Eluting solvent from cartridge_out to to_vessel
            transfer = (out_cartridge_pseudo_flask, step.to_vessel)
            add_transfer_to_dict(transfers, transfer, eluting_volume)

            # from_vessel to cartridge_in
            transfer = (
                step.from_vessel,
                flasks[in_cartridge_pseudo_flask]
            )
            add_transfer_to_dict(transfers, transfer, volume)

            # cartridge_out to to_vessel
            transfer = (
                flasks[out_cartridge_pseudo_flask],
                step.to_vessel
            )
            add_transfer_to_dict(transfers, transfer, volume)

        elif type(step) == FlushTubing:
            if inert_gas_flask:
                transfer = (inert_gas_flask, step.to_vessel)
                add_transfer_to_dict(transfers, transfer, volume)

    return transfers

def add_cartridges_to_flasks(flasks, cartridges):
    """Add cartridge in and out positions to flasks as pseudo flasks."""
    for cartridge in cartridges:
        out_pseudo_flask = cartridge_out_pseudo_flask_name(
            cartridge['chemical'])
        in_pseudo_flask = cartridge_in_pseudo_flask_name(
            cartridge['chemical'])
        flasks[out_pseudo_flask] = out_pseudo_flask
        flasks[in_pseudo_flask] = in_pseudo_flask
    return flasks

def get_optimal_arrangement(
        xdl_obj, graph, flasks, inert_gas_flask, cartridges):
    """Get optimal arrangement of given flasks to minimise transfer distance and
    time.

    Args:
        xdl_obj (XDL): XDL object to use for determining where transfers are
            occurring.
        graph (MultiDiGraph): Graph to find optimal positions in.
        flasks (Dict[str, str]): Flasks to find optimal positions for.
            In dict like this: { chemical: flask_node_name... }
            e.g. { 'toluene': 'flask_toluene' }

    Returns:
        Dict: { flask_node_name: (backbone_index, valve_port) }
               e.g. { 'flask_toluene': (1, 3)... }
    """
    add_cartridges_to_flasks(flasks, cartridges)
    transfers = get_transfers(xdl_obj, graph, flasks, inert_gas_flask)
    backbone = get_backbone(graph, ordered=True)
    flask_nodes = list(flasks.values()) + [inert_gas_flask]
    available_ports = {
        i: get_valve_unused_ports(graph, valve, flask_nodes)
        for i, valve in enumerate(backbone)
    }

    # Get transfers associated with every flask with the backbone position of
    # every flask the reagent is being transferred to.
    flask_transfers = group_transfers_by_flask(
        graph, backbone, flask_nodes, transfers
    )

    # Get position scores
    position_scores = get_position_costs(
        backbone, flask_transfers, flask_nodes
    )

    arrangement = simulated_annealing_optimal_arrangement(
        position_scores,
        available_ports,
        flask_nodes,
    )
    return arrangement

def get_position_costs(
    backbone: List[str],
    flask_transfers: Dict,
    flask_nodes: List[str]
) -> Dict:
    """For every flask get cost associated with every position on backbone.
    Return as dict: { 'flask_toluene': { '0': 1.0, '1': 0.86, '2': 0.5... }... }

    All costs are normalised to 0-1 range by dividing by maximum cost of all
    flasks.

    Args:
        backbone (List[str]): Chemputer backbone
        flask_transfers (Dict): Flask transfers
        flask_nodes (List[str]): List of flask nodes

    Returns:
        Dict: Costs associated with each flask
    """
    max_cost = 0
    position_costs = {
        flask: {
            i: 0 for i in range(len(backbone))
        } for flask in flask_nodes
    }

    # Iterate through all transfers
    for flask, transfers in flask_transfers.items():
        # Get the costs
        flask_costs = position_costs[flask]

        # Enumerate through backbone
        for i in range(len(backbone)):
            # Get the cost
            cost = sum([
                (abs(i - transfer_i) + 1) * volume
                for transfer_i, volume in transfers
            ])

            # Set the cost
            flask_costs[i] = cost

            # Update max cost
            if cost > max_cost:
                max_cost = cost

    # Normalize
    for flask, costs in position_costs.items():
        for i in range(len(costs)):
            if max_cost != 0:
                costs[i] /= max_cost

    return position_costs

def group_transfers_by_flask(
    graph: MultiDiGraph,
    backbone: List[str],
    flasks: List[str],
    transfers: Dict
) -> Dict:
    """Group transfers by flasks. Return dict:
    { flask_node_name: [ (backbone_index, volume)... ]... }

    Args:
        graph (MultiDiGraph): Graph to check
        backbone (List[str]): List of backbone valves
        flasks (List[str]): List of flasks
        transfers (Dict): Transfer information
    """

    flask_transfers = {
        flask: [] for flask in flasks
    }

    # Iterate through all transfers
    for transfer, volume in transfers.items():
        if transfer[0] in flasks:
            flask_list = flask_transfers[transfer[0]]
            other_vessel = transfer[1]
        elif transfer[1] in flasks:
            flask_list = flask_transfers[transfer[1]]
            other_vessel = transfer[0]

        # Get position of other vessel on backbone
        backbone_valve_position = get_backbone_valve_position(
            graph, backbone, other_vessel)

        # If backbone position is found append to list. Sometimes backbone
        # position is not found in the case of buffer flasks. This, and general
        # support for buffer flasks needs to be sorted. TODO.
        if backbone_valve_position is not None:
            flask_list.append((
                backbone_valve_position,
                volume
            ))

    return flask_transfers

def get_backbone_valve_position(
    graph: MultiDiGraph, backbone: List[str], node: str
) -> Optional[int]:
    """Given a node find what position of the backbone it is connected to.

    Args:
        graph (MultiDiGraph): Graph to check
        backbone (List[str]): List of backbone valves
        node (str): Node to check

    Returns:
        Optional[int]: Node position on the backbone, none if not found
    """

    for neighbor in undirected_neighbors(graph, node):
        for i, valve in enumerate(backbone):
            if valve == neighbor:
                return i
    return None

def get_valve_unused_ports(
    graph: MultiDiGraph, valve: str, flask_nodes: List[str]
) -> List[str]:
    """Get unused ports on valve, ignoring reagent flasks as these will be
    removed later.

    Args:
        graph (MultiDiGraph): Graph to check
        valve (str): Valve to check
        flask_nodes (List[str]): List of Flask nodes

    Returns:
        List[str]: List of unused ports on the valve
    """

    used_ports = []

    # Iterate through all graph edges
    for src, dest, data in graph.edges(data=True):
        # Valve is a src
        if src == valve:
            # Get port data and add to used ports
            src_port, dest_port = data['port']
            used_ports.append(str(src_port))

        # Valve is the destination
        elif dest == valve:
            # Src not in the flask nodes
            if src not in flask_nodes:
                # Get port data and add to used ports
                src_port, dest_port = data['port']
                used_ports.append(str(dest_port))

    # Return all unused ports based on used ports
    return [str(i) for i in range(6) if str(i) not in used_ports]

def simulated_annealing_optimal_arrangement(
    position_costs: Dict,
    available_ports: List[str],
    flask_nodes: List[str],
    n_iterations: int = 3000,
    starting_threshold: float = 0.05,
    quenching_iterations: Optional[int] = None,
) -> Dict:
    """Use simulated annealing to find optimum configuration of flasks.

    Exact algorithm used is this:

    - start off with random arrangement of flasks
    - start of with threshold == starting_threshold
    for max_iterations:
        - decrease threshold by increment
        - either swap two flask positions, or move a flask to an unused position
        - if the cost decreases, or it increases but below the threshold
          move to this arrangement as starting point for next iteration
        - if it increases above the threshold, retain the same arrangement for
          the next iteration

    The threshold is decreased on every iterations so that it is 0 for the last
    `quenching_iterations` iterations.
    If `quenching_iterations` is not given then it is calculated as
    `max_iterations` / 20.

    Args:
        position_costs (Dict): Position costs
        available_ports (List[str]): List of available ports to use
        flask_nodes (List[str]): List of flask nodes
        n_iterations (int): Number of iterations to perform
        starting_threshold (float): Threshold
        quenching_iterations (Optional[int]) Number of quenching iterations
                                                Defaults to None

    Returns:
        Dict of flasks and their optimal positions, e.g.
        {
            'flask_toluene': (0, 1) # flask_toluene on first backbone valve,
            port 1
            ...
        }

    NOTE: The default parameters n_iterations=3000 and starting_threshold=0.05
    where chosen after methodically testing n_iterations 100-10000 and
    starting_threshold=0.05-0.5. 3000 and 0.05 seemed to be the best parameters
    (lowest n_iterations) that gave 100% success rate on this very simple test.
    In future it might be worth doing a more thorough test to determine the
    best values for these parameters.
    """
    # Seed random otherwise tests will be non deterministic and you just can't
    # live like that.
    random.seed(25)

    # If quenching iterations not given, calculate default value
    if quenching_iterations is None:
        quenching_iterations = n_iterations / 20

    # Get initial arrangement and cost
    positions = get_all_positions(available_ports)
    arrangement = get_random_arrangement(flask_nodes, positions)
    cost = get_arrangement_cost(arrangement, position_costs)
    for i in range(n_iterations):

        # Calculate threshold based on i
        threshold = max((
            starting_threshold
            - ((starting_threshold / (n_iterations - quenching_iterations)) * i)
        ), 0)

        # Get new arrangement and cost
        new_arrangement = get_new_arrangement(
            arrangement, flask_nodes, positions)
        new_cost = get_arrangement_cost(new_arrangement, position_costs)

        # New cost is less than previous cost, accept change
        if new_cost < cost:
            arrangement = new_arrangement
            cost = new_cost

        # New cost is higher than previous cost, but below threshold, accept
        elif new_cost - cost < threshold:
            arrangement = new_arrangement
            cost = new_cost

    return arrangement

def get_all_positions(available_ports: Dict) -> List[Tuple[int, int]]:
    """Return all available positions in form: [(backbone_index, valve_port)...]

    Args:
        available_ports (Dict[int, List[str]]): List of available ports for
            every backbone position, e.g. { 0: ['3', '4'], 1: ['2']... }

    Returns:
        List[Tuple[int, int]]: Backbone positions and ports
    """

    positions = []
    for backbone_i, ports in available_ports.items():
        for port in ports:
            positions.append((backbone_i, port))

    return positions

def get_random_arrangement(
    flask_nodes: List[str], positions: List[int]
) -> Dict:
    """Get random arrangement of flasks.

    Args:
        flask_nodes (List[str]): List of flask nodes
        positions (List[int]): List of positions

    Returns:
        Dict: { flask_node_name: ( backbone_index, valve_port )... }
    """
    arrangement = {}
    for item in flask_nodes:
        arrangement[item] = random.choice(positions)
    return arrangement

def get_new_arrangement(
    prev_arrangement: Dict,
    flask_nodes: List[str],
    positions: List[int]
) -> Dict:
    """Get new arrangement with random change from previous arrangement. Change
    can either be moving a random node to an unused position, or swapping two
    random nodes.

    Args:
        prev_arrangement (Dict): Previous arrangement
        flask_nodes (List[str]): List of flask nodes
        positions (List[int]): List of positions
    Returns:
        Dict: { flask_node_name: ( backbone_index, valve_port )... }
    """

    used_positions = []
    new_arrangement = copy.deepcopy(prev_arrangement)

    # Iterate through the rpevious arrangement
    for _, position in prev_arrangement.items():
        used_positions.append(position)

    # Get all unused positions
    unused_positions = [
        position
        for position in positions
        if position not in used_positions
    ]

    # Change it up
    changes = unused_positions + flask_nodes
    node_to_change = random.choice(flask_nodes)

    # Cartridge can't have same in / out position.
    if '-cartridge-' in node_to_change:
        cartridge_backbone_pos = new_arrangement[node_to_change][0]
        for i in reversed(range(len(changes))):
            if type(changes[i]) == tuple:
                if cartridge_backbone_pos == changes[i][0]:
                    changes.pop(i)

    change = random.choice(changes)
    while change == node_to_change:
        change = random.choice(changes)

    # Move to unused position
    if change in unused_positions:
        new_arrangement[node_to_change] = change

    # Swap two nodes
    else:
        new_arrangement[node_to_change] = prev_arrangement[change]
        new_arrangement[change] = prev_arrangement[node_to_change]

    return new_arrangement

def get_arrangement_cost(arrangement: Dict, position_costs: Dict) -> float:
    """Get cost of given arrangement. Calculated as mean of all individual
    position costs.

    Args:
        arrangement (Dict): Arrangement to cost
        position_costs (Dict): Costs of the positions

    Returns:
        float: Cost of the arrangement
    """

    cost = 0
    for flask_node, position in arrangement.items():
        backbone_i, _ = position
        cost += position_costs[flask_node][backbone_i]

    cost /= len(arrangement)

    return cost
