import pytest
import os
import pprint

from xdl import XDL
from xdl.utils.graph import get_graph
from xdl.steps.utils import FTNDuration

from chemputerxdl.executor.graph import hardware_from_graph
from chemputerxdl.utils.execution import get_chempiler
from chemputerxdl.scheduling.scheduling import (
    get_component_class_map,
    get_possible_hardware_maps,
    get_all_possible_resource_allocations,
    get_resource_usage_ftns,
    get_resource_usage_times,
    resource_usage_times_are_compatible,
    shift_usage_times,
    merge_usage_times,
    find_optimal_schedule_genetic_algorithm,
    find_optimal_schedule_grid_search,
    find_optimal_schedule_random_search,
    find_optimal_schedule_simulated_annealing,
    get_schedule,
)
from AnalyticalLabware.devices import chemputer_devices

HERE = os.path.abspath(os.path.dirname(__file__))
FILES = os.path.join(HERE, 'files')

TRIFLUOROMETHYLATION_XDL = os.path.join(FILES, 'trifluoromethylation.xdl')
BASIC_PARALLEL_XDL = os.path.join(FILES, 'basic_parallel.xdl')

TWO_REACTORS_GRAPH_F = os.path.join(
    FILES, 'trifluoromethylation_B_two_reactors.json')
THREE_REACTORS_GRAPH_F = os.path.join(
    FILES, 'trifluoromethylation_B_three_reactors.json')
FOUR_REACTORS_GRAPH_F = os.path.join(
    FILES, 'trifluoromethylation_B_four_reactors.json')

@pytest.mark.unit
def test_get_component_class_map():
    """Test that `get_component_class_map` returns all possible hardware
    mappings given a list of XDL components and corresponding hardware
    components. This is basically just a wrapper round ``itertools.products``.
    """
    # Load files
    xdl = XDL(TRIFLUOROMETHYLATION_XDL)
    graphs = [TWO_REACTORS_GRAPH_F, THREE_REACTORS_GRAPH_F]

    # Define expected mappings
    reactor_expected_results = [
        [
            ('reactor', 'reactor1'),
            ('reactor', 'reactor2'),
        ],
        [
            ('reactor', 'reactor1'),
            ('reactor', 'reactor2'),
            ('reactor', 'reactor3')
        ]
    ]

    rotavap_expected_results = [
        [
            ('rotavap', 'rotavap'),
        ],
        [
            ('rotavap', 'rotavap'),
        ]
    ]

    # Run test XDL with different graphs and check mappings are correct.
    for i, graph_name in enumerate(graphs):
        graph = get_graph(graph_name)
        graph_hardware = hardware_from_graph(graph)

        # Test reactors
        maps = get_component_class_map(
            xdl.hardware.reactors, graph_hardware.reactors)
        assert maps == reactor_expected_results[i]

        # Test rotavaps
        maps = get_component_class_map(
            xdl.hardware.rotavaps, graph_hardware.rotavaps)
        assert maps == rotavap_expected_results[i]

@pytest.mark.unit
def test_get_possible_hardware_maps():
    # Load files
    xdl = XDL(TRIFLUOROMETHYLATION_XDL)
    test_graphs = [
        TWO_REACTORS_GRAPH_F,
        THREE_REACTORS_GRAPH_F
    ]

    # Define expected hardware maps
    expected_results = [
        [
            [('reactor', 'reactor1'), ('rotavap', 'rotavap')],
            [('reactor', 'reactor2'), ('rotavap', 'rotavap')],
        ],
        [
            [('reactor', 'reactor1'), ('rotavap', 'rotavap')],
            [('reactor', 'reactor2'), ('rotavap', 'rotavap')],
            [('reactor', 'reactor3'), ('rotavap', 'rotavap')],
        ],
    ]

    # Go through different graphs and check produced hardware maps are correct
    for i, graph_name in enumerate(test_graphs):
        graph = get_graph(graph_name)
        maps = get_possible_hardware_maps(xdl, graph)

        all_mapresult = []
        for m in maps:
            mapresult = []
            for k, v in m.items():
                mapresult.append((k, v))
            all_mapresult.append(mapresult)
        print(all_mapresult)
        assert all_mapresult == expected_results[i]

@pytest.mark.unit
def test_get_all_possible_resource_allocations():
    xdl1 = XDL(TRIFLUOROMETHYLATION_XDL)
    xdl2 = XDL(TRIFLUOROMETHYLATION_XDL)

    xdl_lists = [[xdl1], [xdl1, xdl2]]
    graphs = [TWO_REACTORS_GRAPH_F, THREE_REACTORS_GRAPH_F]

    expected_results = [
        {'n_maps': 1, 'map_size': 2},
        {'n_maps': 1, 'map_size': 3},
        {'n_maps': 2, 'map_size': 2},
        {'n_maps': 2, 'map_size': 3},
    ]

    i = 0
    for xdl_list in xdl_lists:
        for graph_name in graphs:
            graph = get_graph(graph_name)

            result = get_all_possible_resource_allocations(
                xdl_list, graph, device_modules=[chemputer_devices]
            )

            assert len(result) == expected_results[i]['n_maps']
            assert len(result[0]) == expected_results[i]['map_size']
            i += 1

@pytest.mark.unit
def test_get_resource_usage_ftns():

    xdl = XDL(TRIFLUOROMETHYLATION_XDL)
    graph = get_graph(TWO_REACTORS_GRAPH_F)
    chempiler = get_chempiler(graph, device_modules=[chemputer_devices])

    resource_alloc = get_all_possible_resource_allocations(
        [xdl], graph, device_modules=[chemputer_devices]
    )

    # select a single resource alloc
    resource_alloc = resource_alloc[0][0]

    # get ftns for this alloc
    ftns = get_resource_usage_ftns(resource_alloc, graph, chempiler)

    ftns = get_resource_usage_ftns(resource_alloc, graph, chempiler)
    pprint.pprint(ftns)

    # TODO: ADD CHECKS !

@pytest.mark.unit
def test_get_resource_usage_times():
    """Test algorithm is able to correctly determine the times that resources
    may be in use in the best or worst case scenario of all preceding steps.
    """

    graph = get_graph(TWO_REACTORS_GRAPH_F)
    chempiler = get_chempiler(graph, device_modules=[chemputer_devices])

    example_res_use = [
        (FTNDuration(1, 5, 11),
         ['reactor1', 'pump1']),
        (FTNDuration(1, 5, 11),
         ['reactor1', 'pump1']),
        (FTNDuration(1, 5, 12),
         ['reactor2']),
        (FTNDuration(1, 5, 13),
         ['reactor3']),
        (FTNDuration(10, 10, 10),
         ['reactor2']),
    ]

    example_answers = {
        'reactor1': [[0, 22]],
        'pump1': [[0, 22]],
        'reactor2': [[2, 34], [4, 57]],
        'reactor3': [[3, 47]],
    }

    resource_usage, _ = get_resource_usage_times(
        example_res_use, chempiler)
    pprint.pprint(resource_usage)

    for node, usage_times in resource_usage.items():
        assert usage_times == example_answers[node]

@pytest.mark.unit
def test_resource_usage_times_are_compatible():
    """Check function for determining if two resource usage times are
    compatible, i.e. the times don't overlap.
    """
    examples = [
        (True, (
            {'reactor1': [[0, 10]]},
            {'reactor1': [[11, 20]]}
        )),
        (False, (
            {'reactor1': [[0, 10]]},
            {'reactor1': [[5, 15]]}
        )),
        (False, (
            {'reactor1': [[5, 15]]},
            {'reactor1': [[0, 10]]}
        )),
        (False, (
            {'reactor1': [[5, 10]]},
            {'reactor1': [[0, 15]]}
        )),
        (False, (
            {'reactor1': [[0, 15]]},
            {'reactor1': [[5, 10]]}
        )),
        (False, (
            {
                'reactor1': [[0, 10]],
                'pump1': [[0, 10]],
            },
            {
                'reactor2': [[0, 10]],
                'pump1': [[0, 10]],
            },
        ))
    ]
    for example in examples:
        print(example)
        assert example[0] is resource_usage_times_are_compatible(
            example[1][0], example[1][1])

@pytest.mark.unit
def test_merge_usage_times():
    """Test function for merging two sets of resource usage times into one dict.
    """
    t1 = {'pump_1': [[1, 10], [12, 20]],
          'pump_2': [[1, 10], [12, 20]]}

    t2 = {'pump_1': [[21, 30], [31, 40]],
          'pump_2': [[21, 30], [31, 45]],
          'pump_3': [[1, 10]]}

    block_shift = 0
    while not resource_usage_times_are_compatible(
            t1, t2):
        block_shift += 1
        t2 = shift_usage_times(t2, 1)

    merged = merge_usage_times(t2, t1)

    expected = {'pump_1': [[1, 10], [12, 20], [21, 30], [31, 40]],
                'pump_2': [[1, 10], [12, 20], [21, 30], [31, 45]],
                'pump_3': [[1, 10]]}

    assert merged == expected

def test_algorithm(algorithm: str):
    """Test that given algorithm runs without error and obtains correct result.
    Possible algorithms: 'ga', 'sa', 'rs', 'gs'
    """
    # minimal example, parallelise across reactors.
    example_usage_times = [
        [
            {'pump': [[0, 10]], 'reactor1': [[10, 50]]},
            {'pump': [[0, 10]], 'reactor2': [[10, 50]]},
            {'pump': [[0, 10]], 'reactor3': [[10, 50]]}
        ],
        [
            {'pump': [[0, 10]], 'reactor1': [[10, 50]]},
            {'pump': [[0, 10]], 'reactor2': [[10, 50]]},
            {'pump': [[0, 10]], 'reactor3': [[10, 50]]}
        ],
        [
            {'pump': [[0, 10]], 'reactor1': [[10, 50]]},
            {'pump': [[0, 10]], 'reactor2': [[10, 50]]},
            {'pump': [[0, 10]], 'reactor3': [[10, 50]]}
        ],
    ]

    solvers = {
        'ga': find_optimal_schedule_genetic_algorithm,
        'sa': find_optimal_schedule_simulated_annealing,
        'rs': find_optimal_schedule_random_search,
        'gs': find_optimal_schedule_grid_search,
    }

    shortest_combo, shortest_start_times = \
        solvers[algorithm](example_usage_times)

    import itertools
    expected_shortest_combos = list(itertools.permutations((
        {'pump': [[0, 10]], 'reactor1': [[10, 50]]},
        {'pump': [[0, 10]], 'reactor2': [[10, 50]]},
        {'pump': [[0, 10]], 'reactor3': [[10, 50]]}
    )))

    # cannot parallelize across pump, so pump node use
    # is staggered.
    expected_start_times = [0, 11, 22]

    print('shortest combo:')
    pprint.pprint(shortest_combo)

    print('start times:')
    pprint.pprint(shortest_start_times)

    assert shortest_combo in expected_shortest_combos
    assert shortest_start_times == expected_start_times

@pytest.mark.unit
def test_find_optimal_schedule_genetic_algorithm():
    """Test GA runs without error and gets correct result."""
    test_algorithm('ga')

@pytest.mark.unit
def test_find_optimal_schedule_grid_search():
    """Test grid search runs without error and gets correct result."""
    test_algorithm('gs')

@pytest.mark.unit
def test_find_optimal_schedule_random_search():
    """Test grid search runs without error and gets correct result."""
    test_algorithm('rs')

# @pytest.mark.unit
def test_find_optimal_schedule_simulated_annealing():
    """Test grid search runs without error and gets correct result."""
    test_algorithm('sa')

@pytest.mark.unit
def test_schedule_block_to_json():
    """Test conversion of packaged parallel info to json.
    """
    xdl_f = BASIC_PARALLEL_XDL

    xdl1 = XDL(xdl_f)

    xdl_schedule = get_schedule(
        [xdl1],
        TWO_REACTORS_GRAPH_F,
        device_modules=[chemputer_devices]
    )
    xdl_schedule.to_json()
