"""This is a rewrite of the code in parallelizer.py, but using fuzzy job shop
scheduling problem (FJSSP) terminology. It follows roughly the same algorithm,
but abandons the lock matrix. Instead, step durations are represented as fuzzy
triangular numbers (FTNs), and overlap of two blocks is detected directly with
these.

Decided to package everything into a list of ``ParallelizedBlock`` objects,
inside which you have all the info on node usage, step start and end times,
node usage for individual steps etc. These have a to_json method to
export stuff for visualisation. If I understand correctly, these should be
easy to map through and visualise on the other end.

Now even with 4 XDLs and a 4-reactor graph it is kind of tractable with
brute force.

TODO:
- Need to throw and error / warning / reject parallelisation when trying
  to schedule a second block where one of the nodes it intends to use is
  locked by a previous block. At the moment it just silently "parallelized"
  with a makespan reduction of zero.

- Make execution stream from the list of ``ParallelizedBlocks``.

- Find a way to benchmark algorithms.


--------
Couple of things I changed / fixed you may want to double check:

    - stopped applying ongoing locks to nodes with "waste" in the name.
      I guess one could do something more general for any node that
      shouldn't be ongoing locked. If you don't do this the reduction in
      makespan is basically zero when parallelizing.

    - changed the conditions for compatability of node_use dicts.
      The conditions as they were didn't cover all cases of incompat.

    - rewrote merge_useage_times, old version broken.

    - Implemented a simple genetic algorithm.

    - Implemented random search (baseline non-exhaustive algorithm).
"""
from typing import List, Dict, Union, Tuple
from types import ModuleType
import copy
import random
import itertools
from math import exp
from networkx import MultiDiGraph
from chempiler import Chempiler

# XDL imports
from xdl import XDL
from xdl.utils.logging import get_logger
from xdl.hardware import Component
from xdl.steps.utils import FTNDuration
from xdl.utils.graph import get_graph

# Relative imports
from .classes import ScheduleStep, ScheduleBlock, XDLSchedule
from .utils import shift_usage_times
from ..executor.graph import hardware_from_graph
from ..utils.execution import get_chempiler

def get_schedule(
    xdls: List[XDL],
    graph: Union[str, MultiDiGraph],
    device_modules: List[ModuleType] = [],
    solver_method='grid_search',
    **kwargs
):
    """Get optimal parallel schedule for given list of XDLs being executed on
    given graph.

    Args:
        xdls (List[XDL]): List of XDLs to be scheduled in parallel.
        graph (Union[str, MultiDiGraph]): Path to graph file or graph object
            that XDLs will be executed on.
        device_modules (List[ModuleType]): List of device modules to pass to
            ``Chempiler`` constructor. ``ChemputerAPI`` is passed by default so
            this is just for anything extra like ``AnalyticalLabware``.
        solver_method (str): Method to use when searching for optimal schedule.
             Options: 'grid_search', 'simulated_annealing', 'genetic_algorithm'.

    Returns:
        list[ParallelizedBlock]: Info on parallelized XDL blocks for later use.
    """
    # If graph is a file convert it to `MultiDiGraph`
    graph = get_graph(graph)

    # Get all possible resource allocations for each block. Store as a list of
    # blocks for each item in `blocks`.
    # e.g.
    # [
    #     [
    #         [block1_step1_resource_allocation1...],
    #         [block1_step1_resource_allocation2...]
    #     ],
    #     [
    #         [block2_step1_resource_allocation1...],
    #         [block2_step1_resource_allocation2...]
    #      ],
    # ]
    xdl_resource_allocations = get_all_possible_resource_allocations(
        xdls, graph, device_modules=device_modules)

    # Create a chempiler object to use for obtaining step locks
    chempiler = get_chempiler(graph, device_modules=device_modules)

    # Make a list in the same structure as `xdl_resource_allocations`, but
    # for each resource allocation instead of a list of steps you have a
    # Dict[str, List[List[int]]] giving the times that each node could be in
    # use in the best and worst case scenarios for all preceding steps. E.g.
    # [
    #     [
    #         {
    #             reactor1: [[0, 1], [315, 400]...],
    #             ...
    #         },
    #         {
    #             reactor2: [[0, 1], [315, 400]...],
    #             ...
    #         },
    #     ],
    #     [
    #         {
    #             reactor1: [[0, 1], [100, 1111...],
    #             ...
    #         },
    #         {
    #             reactor2: [[0, 1], [100, 1111]...],
    #             ...
    #         },
    #      ],
    # ]

    all_resource_usage_times = get_all_resource_usage_times(
        xdl_resource_allocations, graph, chempiler)

    # Use resource usage times to search for optimal schedule.
    optimal_combo, optimal_block_start_times = find_optimal_schedule(
        all_resource_usage_times, method=solver_method, **kwargs)

    # use the optimised combo to get the corresponding resource-allocated
    # XDL block.
    optimal_xdl_blocks, optimal_usage_times = [], []
    for i, all_alloc_usage_times in enumerate(all_resource_usage_times):
        for j, usage_time in enumerate(all_alloc_usage_times):
            if optimal_combo[i] == usage_time:
                optimal_xdl_blocks.append(xdl_resource_allocations[i][j])
                optimal_usage_times.append(usage_time)

    # Package parallelized block info and return
    return package_parallelized_blocks(
        optimal_xdl_blocks,
        optimal_block_start_times,
        optimal_usage_times,
        graph,
        chempiler
    )

def package_parallelized_blocks(
    optimal_xdl_blocks: List[XDL],
    optimal_block_start_times: List[int],
    optimal_usage_times: List[Dict[str, List[int]]],
    graph: MultiDiGraph,
    chempiler: Chempiler
) -> List[ScheduleBlock]:
    """Conveniently package XDL blocks and their parallelization
    info for later use.

    Args:
        optimal_xdl_blocks (List[XDL]): Chosen hardware-mapped XDL from
            schedule optimization algorithm.
        optimal_block_start_times (List[int]): Optimized XDL start times.
            One for each XDL block.
        optimal_usage_times (List[Dict[str, List[int]]]): Optimized node
            use times.
        chempiler (Chempiler): Chempiler used to compute base step node
            use and durations for each step in each XDL block.

    Returns:
        List[ParallelizedBlock]: [description]
    """
    # Package chosen xdl objects and parallelization info.
    parallelized_blocks = []
    for i, block in enumerate(optimal_xdl_blocks):
        _, step_ftns = get_resource_usage_ftns(block, graph, chempiler)

        # Go through each step within this block and get node
        # use for that step only, then create a ParallelizedStep.
        cum_minmax = (0, 0)
        parallelized_steps = []
        for j, xdl_step in enumerate(block.steps):

            # We supply the current cumulative time
            node_use, cum_minmax = get_resource_usage_times(
                step_ftns[j], chempiler, cum_minmax=cum_minmax
            )

            # Add ParallelizedStep to list of parallelized steps.
            parallelized_steps.append(
                ScheduleStep(
                    xdl_step, optimal_block_start_times[i], node_use)
            )

        # Add block to list of parallelized blocks
        parallelized_blocks.append(
            ScheduleBlock(
                block_id=f'xdl_block_{i}',
                start_time=optimal_block_start_times[i],
                xdl_obj=optimal_xdl_blocks[i],
                steps=parallelized_steps,
                node_use=optimal_usage_times[i],
            )
        )

    return XDLSchedule(parallelized_blocks, graph)

def get_component_class_map(
    xdl_components: List[Component], graph_components: List[Component]
):
    """Retrieve possible XDL to Graph hardware maps for a given
    component class (reactor, separator, filter or rotavap).

    Args:
        xdl_components (List[Component]): xdl components of given class
        graph_components (List[Component]): graph components of given class

    Returns:
        List[List[str, str]]: Corresponding xdl and graph component IDs
            for each hardware map.

    """
    # Iterate through all graph component permutations and map to
    # list of xdl components.
    component_map = []
    for c_xdl, c_graph in itertools.product(xdl_components, graph_components):
        component_map.append((c_xdl.id, c_graph.id))
    return component_map


def get_possible_hardware_maps(xdl_obj: XDL, graph: MultiDiGraph):
    """Get all possible maps of XDL step components to graph hardware

    Args:
        xdl_obj (XDL): XDL object to find possible mappings for.

    Returns:
        List[Dict[str, str]]: For each valid hardware map, the
            corresponding XDL and graph hardware IDs to be passed to
            ``prepare_for_execution``.

    """
    graph_hardware = hardware_from_graph(graph)

    # Determine valid maps for reactors
    map_reactors = get_component_class_map(
        xdl_obj.hardware.reactors, graph_hardware.reactors
    )

    # Determine valid maps for filters
    map_filters = get_component_class_map(
        xdl_obj.hardware.filters, graph_hardware.filters
    )

    # Determine valid maps for separators
    map_separators = get_component_class_map(
        xdl_obj.hardware.separators, graph_hardware.separators
    )

    # Determine valid maps for rotavaps
    map_rotavaps = get_component_class_map(
        xdl_obj.hardware.rotavaps, graph_hardware.rotavaps
    )

    # Compile all maps for hardware reqired by XDL
    map_all = [
        m
        for m in [map_reactors, map_filters, map_separators, map_rotavaps]
        if len(m) > 0
    ]

    # Convert maps to dictionaries to be passed to prepare_for_execution
    hardware_map_dicts = []
    for m in itertools.product(*map_all):
        map_dict = {}
        for c_xdl, c_graph in m:
            map_dict[c_xdl] = c_graph
        hardware_map_dicts.append(map_dict)

    return hardware_map_dicts


def get_all_possible_resource_allocations(
    xdls: List[XDL],
    graph: MultiDiGraph,
    device_modules: List[ModuleType] = []
) -> List[List[XDL]]:
    """Get XDL objects for all possible resource allocations of given XDL
    objects on given graph. The list returned will be the same as the `xdls`,
    but for every XDL object in the original list there will be a list of
    compiled XDL objects in the returned list, corresponding to all different
    resource allocations for that XDL.

    Args:
        xdls (List[XDL]): List of XDLs to find possible resource allocations
            for.
        graph (MultiDiGraph): Graph to use for finding possible resource
            allocations.
        device_modules (List[ModuleType]): List of device modules to pass to
            ``Chempiler`` constructor. ``ChemputerAPI`` is passed by default so
            this is just for anything extra like ``AnalyticalLabware``.

    Returns:
        List[List[XDL]]: Same as `xdls`, but for every XDL object in the
        original list there will be a list of compiled XDL objects in the
        returned list, corresponding to all possible resource allocations for
        that XDL.
    """
    all_resource_allocations = []

    # Go through each xdl block, get possible hardware maps and create
    # new xdl objects for each hardware map
    for xdl_obj in xdls:
        # Get all possible hardware maps
        hardware_maps = get_possible_hardware_maps(xdl_obj, graph)

        # Append new list for this XDL object.
        all_resource_allocations.append([])

        # Go through all hardware maps and compile a new XDL object with each
        # one and append to `all_resource_allocations` list for this `xdl_obj`.
        for hardware_map in hardware_maps:
            xdl_obj_resource_allocation = copy.deepcopy(xdl_obj)
            xdl_obj_resource_allocation.prepare_for_execution(
                graph,
                hardware_map=hardware_map,
                interactive=False,
                full_procedure=False,
                device_modules=device_modules,
            )
            all_resource_allocations[-1].append(xdl_obj_resource_allocation)

    return all_resource_allocations


def get_resource_usage_ftns(
    xdl_obj: XDL,
    graph: MultiDiGraph,
    chempiler: Chempiler
) -> Dict[str, List[FTNDuration]]:
    """For every node in the graph, get a list of fuzzy triangular numbers
    (FTNs) for every base step in which the node is used. FTNs are represented
    using the ``FTNDuration`` class.

    Args:
        block (List[Step]): List of steps to get resource usage for.
        chempiler (Chempiler): ``Chempiler`` object to use to get step locks.

    Returns:
        Dict[str, List[FTNDuration]]: Dict of nodes with a list of all the
            times they could be in used represented by FTNs in the form of
            ``FTNDuration`` objects.
    """
    # Resource usage fuzzy triangular numbers (represented using FTNDuration
    # class) for every node.
    resource_ftns = []

    # Keep track of ftns within each step to export later
    all_step_ftns = []

    # Track which nodes are under an ongoing lock during the for loop.
    ongoing_lock_tracker = {node: False for node in chempiler.graph}

    # Go through block and get FTNs for all base step node locks.
    for step in xdl_obj.steps:

        step_ftns = []
        for base_step in step.base_steps:

            # Get base step locks
            temporary_locks, ongoing_locks, unlocks = base_step.locks(chempiler)
            base_step_duration = base_step.duration(graph)

            # Update ongoing lock tracker with unlocks and new ongoing locks
            for node in unlocks:
                ongoing_lock_tracker[node] = False

            for node in ongoing_locks:
                if 'waste' not in node:
                    ongoing_lock_tracker[node] = True

            step_ftns.append((
                base_step_duration,
                [
                    node
                    for node, state in ongoing_lock_tracker.items()
                    if state is True and node not in temporary_locks
                ] + temporary_locks
            ))

        all_step_ftns.append(step_ftns)
        resource_ftns.extend(step_ftns)

    return resource_ftns, all_step_ftns


def get_resource_usage_times(
    resource_usage_ftns: List[Tuple[FTNDuration, List[str]]],
    chempiler: Chempiler,
    cum_minmax: Tuple[int] = (0, 0)
) -> Tuple[Dict[str, List[List[int]]], Tuple[int]]:
    """Get times at which every node could be in use taken best and worst case
    time scenario of all preceding steps into consideration.

    Args:
        resource_usage_ftns (List[Tuple[FTNDuration, List[str]]]): Step
            durations and nodes in use at that step for all steps in procedure.
        chempiler (Chempiler): Chempiler object instantiated with graph that
            ``xdl_obj`` was compiled with.
        cum_minmax (optional, Tuple[int]): Starting FTN min and max for step.
            Used when calculating node use individualy for every step in a
            XDL block.

    Returns:
        Tuple[Dict[str, List[List[int]]], Tuple[int]]: Times at which every
            node could be in use. FTN min and max at end of step / block.
    """
    # Dict to store usage times for every node in. This is returned.
    resource_usage_times = {}

    # Cumulative min and max duration, i.e. `cum_min` is the best case scenario
    # for all preceding steps, `cum_max` is the worst case scenario for all
    # preceding steps.
    cum_min, cum_max = cum_minmax

    # List to track what steps were locked in the previous steps. Used to extend
    # the last usage time if the step was also locked in the previous step,
    # rather than create a new usage time for every step.
    prev_locked_nodes = []

    # Go through and calculate usage times.
    for step_duration, locked_nodes in resource_usage_ftns:

        # Go through all nodes locked by current step
        for node in locked_nodes:

            # If the node has not been previously encountered create a new list
            # to store its usage times.
            if node not in resource_usage_times:
                resource_usage_times[node] = []

            # If the node was also locked in the previous step, extend the last
            # usage time.
            if node in prev_locked_nodes:
                resource_usage_times[node][-1][1] = cum_max + step_duration.max

            # If the node was not locked in the previous step, create a new
            # usage time.
            else:
                resource_usage_times[node].append([
                    cum_min, cum_max + step_duration.max
                ])

        # Update cumulative min / max times.
        cum_min += step_duration.min
        cum_max += step_duration.max

        # Store locked nodes for use on next iteration.
        prev_locked_nodes = locked_nodes

    return resource_usage_times, (cum_min, cum_max)


def get_all_resource_usage_times(
    xdl_resource_allocations: List[List[XDL]],
    graph: MultiDiGraph,
    chempiler: Chempiler
) -> List[List[Dict[str, List[int]]]]:
    """Translate the list of resource-allocated XDL for each user-supplied XDL
    into a dict of times at which each node could be in use during the
    procedure.

    Args:
        xdl_resource_allocations (List[List[XDL]]): List of resource allocations
            for each supplied XDL.
        chempiler (Chempiler): ``Chempiler`` object to use to get step locks.

    Returns:
        List[List[Dict[str, List[int]]]]: [description]
    """

    all_resource_usage_times = []
    for block_resource_allocation_list in xdl_resource_allocations:
        all_resource_usage_times.append([])
        for resource_allocation in block_resource_allocation_list:
            # Get nodes locked and duration FTN for every step in procedure.
            ftns, _ = get_resource_usage_ftns(
                resource_allocation, graph, chempiler)
            all_resource_usage_times[-1].append(
                get_resource_usage_times(ftns, chempiler)[0])
    return all_resource_usage_times


def get_min_overlap(
    usage_times1: Dict[str, List[List[int]]],
    usage_times2: Dict[str, List[List[int]]]
) -> float:
    """Get minimum time overlap between two sets of node use dicts.

    Args:
        usage_times1 (Dict[str, List[List[int]]]): First usage times dict
        usage_times2 (Dict[str, List[List[int]]]): Second usage times dict

    Returns:
        float: Minimum overlap between node uses.
    """
    overlaps = []
    for node in usage_times1:

        # no overlap if node not used in both times
        if node not in usage_times2:
            continue

        for use1 in usage_times1[node]:
            for use2 in usage_times2[node]:

                start1 = use1[0]
                end1 = use1[1]

                start2 = use2[0]
                end2 = use2[1]

                if end1 <= start2:
                    break
                elif end2 <= start1:
                    continue

                # compute overlap
                total = max([end1, end2]) - min([start1, start2])
                delta_start = abs(start1 - start2)
                delta_end = abs(end1 - end2)
                overlap = total - delta_start - delta_end

                overlaps.append(overlap)

    if not overlaps:
        return 1

    return min(overlaps) + 1


def resource_usage_times_are_compatible(
    usage_times1: Dict[str, List[List[int]]],
    usage_times2: Dict[str, List[List[int]]]
) -> bool:
    """Determine if two usage times dicts are compatible. They are compatible if
    there is no overlap in usage times for any nodes.

    Args:
        usage_times1 (Dict[str, List[List[int]]]): First usage times dict
        usage_times2 (Dict[str, List[List[int]]]): Second usage times dict

    Returns:
        bool: ``True`` if usage times don't overlap, otherwise ``False``.
    """
    # Go through all nodes and usage times in the first dict
    for node, node_usage_times1 in usage_times1.items():

        # Only need to check node if it is in the second dict
        if node in usage_times2:

            # Get usage times for node from second dict.
            node_usage_times2 = usage_times2[node]

            # Go through all usage times for current node in first dict
            for usage_time1 in node_usage_times1:

                # Go through all usage times for current node in second dict
                for usage_time2 in node_usage_times2:

                    # Unpack usage times
                    min1, max1 = usage_time1
                    min2, max2 = usage_time2

                    # Check if there is overlap between usage times and return
                    # ``False`` if there is.
                    if (min2 <= min1 <= max2 or min1 <= min2 <= max1):
                        return False

                    # No point going any further as have all further usage times
                    # from the second dict will be past the time from the first
                    # dict.
                    if usage_time2[0] > usage_time1[1]:
                        break

    return True


def evaluate_block_combo(
    block_combo: List[Dict[str, List[List[int]]]]
) -> Tuple[int, List[int]]:
    """Evaluate a combination of blocks by computing their makespan.

    Args:
        block_combo (List[Dict[str, List[List[int]]]): List of XDL node
            use times to consder when computing shortest makespan.

    Returns:
        Tuple[int, List[int]]: Shortest makespan and list of block start
            times for each block in combination.
    """
    # Initialize a list to store block start times in. All times start at 0
    # and are then shifted to create a valid schedule.
    block_start_times = [0 for _ in range(len(block_combo))]

    #: Usage times dict to hold node usage times across multiple blocks,
    #: as block start times are solidified.
    solidified_usage_times = {}

    # Go through every usage times dict in the combo. Leave the first one
    # starting at 0, then shift the others so that there is no overlap
    # between node usage times.
    for i, block in enumerate(block_combo):

        # First block will start at 0
        if i == 0:
            solidified_usage_times = block
            continue

        # Shift block until it doesn't overlap with solidified node usage.
        block_shift = 0
        while not resource_usage_times_are_compatible(
                block, solidified_usage_times):
            shift = get_min_overlap(block, solidified_usage_times)
            block_shift += shift
            block = shift_usage_times(block, shift)

        # Update solidified usage times with this block at valid start time
        block_start_times[i] = block_shift
        solidified_usage_times = merge_usage_times(
            solidified_usage_times, block)

    # Get makespan of this combo
    makespan = 0
    for i, block in enumerate(block_combo):
        for _, usage_times in block.items():
            makespan = max(
                makespan,
                max(
                    usage_times,
                    key=lambda item: item[1]
                )[1] + block_start_times[i]
            )

    return makespan, block_start_times

def merge_usage_times(
    usage_times1: Dict[str, List[List[int]]],
    usage_times2: Dict[str, List[List[int]]]
) -> Dict[str, List[List[int]]]:
    """Merge two usage times dicts. Returns a new dict leaving original dicts
    unaffected. Everything deep copied so there should be no spooky action at a
    distance.

    Args:
        usage_times1 (Dict[str, List[List[int]]]): First usage times dict
        usage_times2 (Dict[str, List[List[int]]]): Second usage times dict

    Returns:
        Dict[str, List[List[int]]]: New usage times dict with given usage times
            dicts merged into one.
    """
    merged_times = copy.deepcopy(usage_times1)

    # Populate merged times with all node use of incoming dicts
    for node in usage_times2:
        if node not in merged_times:
            merged_times[node] = copy.deepcopy(usage_times2[node])
        else:
            merged_times[node] = merged_times[node] + \
                copy.deepcopy(usage_times2[node])

    # Sort merged times for each node by start time
    for node in merged_times:
        merged_times[node].sort(key=lambda x: x[0])

    return merged_times


def find_optimal_schedule_grid_search(
    resource_usage_times: List[List[Dict[str, List[List[int]]]]],
    **kwargs
) -> Tuple[List[Dict[str, List[int]]], List[int]]:
    """Find the optimal schedule for the given resource usage times with a brute
    force search.

    Args:
        resource_usage_times (List[List[Dict[str, List[List[int]]]]]): Resource
            usage times as returned by `get_resource_usage_times`.
    Returns:
        Tuple[int, List[int]]: Shortest makespan and list of block start
            times for each block in optimal combination.
    """
    # Get all possible combos of different resource allocations.
    combos = itertools.product(*resource_usage_times)

    # Initialize variables to store the best found schedule
    shortest_makespan = None
    shortest_makespan_combo = None
    shortest_makespan_block_start_times = None

    # Go through all combos and find the optimal schedule
    for combo in combos:
        makespan, block_start_times = evaluate_block_combo(combo)

        # If this is the shortest makespan found so far, store it to return
        # outside the loop.
        if shortest_makespan is None or makespan < shortest_makespan:
            shortest_makespan = makespan
            shortest_makespan_combo = combo
            shortest_makespan_block_start_times = block_start_times

    return shortest_makespan_combo, shortest_makespan_block_start_times


def find_optimal_schedule_random_search(
    resource_usage_times: List[List[Dict[str, List[List[int]]]]],
    generations: int = 50,
    **kwargs
) -> Tuple[List[Dict[str, List[int]]], List[int]]:
    """Simple random search for optimising resource allocation.

    Args:
        resource_usage_times (List[List[Dict[str, List[List[int]]]]]):
            Possible resource allocations for this graph and supplied
            XDL tasks.
        generations (int, optional): Number of generations search will
            run for. Defaults to 10.

    Returns:
        Tuple[List[Dict[str, List[int]]], List[int]]: Resource allocation
            and and start time for for each block.
    """
    logger = get_logger()

    # Get all combos that we will randomly draw from
    all_combos = list(itertools.product(*resource_usage_times))
    best_makespan = None

    for gen in range(generations):

        # Select random combination of resource allocations
        combo = random.choice(all_combos)

        # Get fitness of this combination
        fitnesses = evaluate_block_combo(combo)[0]

        # Record best makespan and combination
        if best_makespan is None:
            best_makespan = fitnesses
            best_combo = copy.deepcopy(combo)
        if fitnesses < best_makespan:
            best_makespan = fitnesses
            best_combo = copy.deepcopy(combo)

        logger.info(f'Generation: {gen}, Shortest Makespan: {best_makespan}')

    makespan, start_times = evaluate_block_combo(best_combo)
    return tuple(best_combo), start_times

def find_optimal_schedule_simulated_annealing(
    resource_usage_times: List[List[Dict[str, List[List[int]]]]]
):
    pass


def find_optimal_schedule_genetic_algorithm(
    resource_usage_times: List[List[Dict[str, List[List[int]]]]],
    generations: int = 10,
    population_size: int = 10,
    **kwargs
) -> Tuple[List[Dict[str, List[int]]], List[int]]:
    """Genetic algorithm for optimising resource allocation.

    Args:
        resource_usage_times (List[List[Dict[str, List[List[int]]]]]):
            Possible resource allocations for this graph and supplied
            XDL tasks.
        generations (int, optional): Number of generations genetic
            algorithm will run for. Defaults to 10.
        population_size (int, optional): Size of the genetic algorithm
            population. Defaults to 10.

    Returns:
        Tuple[List[Dict[str, List[int]]], List[int]]: Resource allocation
            and and start time for for each block.
    """
    logger = get_logger()

    def select(fitnesses: List[int], max_makespan: int) -> List[int]:
        """Roulette selection method. ndividuals are selected with probability
        proportional to their fitness.

        Args:
            fitnesses (List[int]): Calculated fitness for each individual in
                population.
            max_makespan (int): Worst-case makespan for this set of XDL.

        Returns:
            List[int]: Indices of individuals in population to be selected.
        """
        pop_size = len(fitnesses)
        fitnesses_norm = [f / max_makespan for f in fitnesses]

        # Transofrm fitness with gaussian func to allow minimisation
        fitnesses_func = [exp(-f ** 2) for f in fitnesses_norm]

        return random.choices(
            range(pop_size),
            k=pop_size,
            weights=fitnesses_func
        )

    def mutate(
        combo: List[Dict[str, List[int]]],
        probability: float = 0.2
    ) -> List[Dict[str, List[int]]]:
        """Mutation operation. With probability, switches a given resource use
        with another for each resource use in the combination of resource uses.

        Args:
            combo (List[Dict[str, List[int]]]): resource use combo to be
                mutated.
            probability (float, optional): Probability with which a resource use
                is mutated. Defaults to 0.2.

        Returns:
            List[Dict[str, List[int]]]: Mutated resource use combo.
        """
        for i in range(len(combo)):
            if random.uniform(0, 1) < probability:
                combo[i] = random.choice(resource_usage_times[i])
        return combo

    # Slow, improve by not using generator
    all_combos = list(itertools.product(*resource_usage_times))
    best_makespan = None

    # Population size can't be less than the number of combos, so reduce if
    # necessary.
    population_size = min(len(all_combos), population_size)

    # Initialize population (convert combos to lists so they can be mutated)
    population = copy.deepcopy(random.sample(all_combos, k=population_size))
    population = [list(p) for p in population]

    # Get worst-case makespan (used to normalise fitness)
    max_makespan = 0
    for alloc in all_combos[0]:
        times = list(
            itertools.chain.from_iterable(
                itertools.chain.from_iterable(
                    [t for t in alloc.values()]
                )
            )
        )
        max_makespan += max(times) - min(times)

    for gen in range(generations):

        # Get fitnesses
        fitnesses = [evaluate_block_combo(p)[0] for p in population]

        # Record best makespan and combo
        for i, f in enumerate(fitnesses):
            if best_makespan is None:
                best_makespan = f
                best_combo = copy.deepcopy(population[i])
            if f < best_makespan:
                best_makespan = f
                best_combo = copy.deepcopy(population[i])

        # Select new population based on fitnesses (roulette)
        new_pop_indices = select(fitnesses, max_makespan)
        population = [copy.deepcopy(population[i]) for i in new_pop_indices]

        # Mutate new population
        population = [copy.deepcopy(mutate(p)) for p in population]

        logger.info(f'Generation: {gen}, Shortest Makespan: {best_makespan}')

    makespan, start_times = evaluate_block_combo(best_combo)
    return tuple(best_combo), start_times


#: Dict to map solver algorithm keyword to function
schedule_solvers = {
    'grid_search': find_optimal_schedule_grid_search,
    'random_search': find_optimal_schedule_random_search,
    'simulated_annealing': find_optimal_schedule_simulated_annealing,
    'genetic_algorithm': find_optimal_schedule_genetic_algorithm,
}

def find_optimal_schedule(
    resource_usage_times,
    method='simulated_annealing',
    *args, **kwargs
):
    """Find optimal schedule using given schedule.

    Args:
        resource_usage_times (List[List[Dict[str, List[List[int]]]]]): Resource
            usage times as returned by `get_resource_usage_times`.
        solver_method (str): Method to use when searching for optimal schedule.
            Options: 'grid_search', 'simulated_annealing'.

    Returns:
        ?: Optimal schedule. Format yet to be decided.
    """
    return schedule_solvers[method](resource_usage_times, *args, **kwargs)
