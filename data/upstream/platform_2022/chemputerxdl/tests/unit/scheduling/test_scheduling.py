import pytest
import os
import time
import json
from AnalyticalLabware.devices import chemputer_devices

from xdl import XDL
from xdl.steps import Await, Async, Wait

from chemputerxdl.scheduling.scheduling import get_schedule

HERE = os.path.abspath(os.path.dirname(__file__))
FILES = os.path.join(HERE, 'files')
OUTPUT_FILES = os.path.join(HERE, 'test_output')
os.makedirs(OUTPUT_FILES, exist_ok=True)

TRIFLUOROMETHYLATION_XDL = os.path.join(FILES, 'trifluoromethylation.xdl')
BASIC_PARALLEL_XDL = os.path.join(FILES, 'basic_parallel.xdl')

TWO_REACTORS_GRAPH_F = os.path.join(
    FILES, 'trifluoromethylation_B_two_reactors.json')
THREE_REACTORS_GRAPH_F = os.path.join(
    FILES, 'trifluoromethylation_B_three_reactors.json')
FOUR_REACTORS_GRAPH_F = os.path.join(
    FILES, 'trifluoromethylation_B_four_reactors.json')

SPLIT_GRAPH_TESTS = [
    (('split-graph-addition-1.xdl', 'split-graph-addition-2.xdl'),
     'simple-two-valve-graph.json'),
]

STAGGERED_START_TESTS = [
    (
        ('staggered-addition-1.xdl', 'staggered-addition-1.xdl'),
        'simple-two-valve-graph.json',
    )
]

@pytest.mark.unit
def test_split_graph_scheduling():
    """Test that the situation where the graph is effectively split down the
    middle and a different XDL is ran on each side works.
    """
    # Go through all tests
    for xdl_files, graph_f in SPLIT_GRAPH_TESTS:
        graph_f = os.path.join(FILES, graph_f)

        # Instantiate XDL objects
        xdl_objs = [XDL(os.path.join(FILES, xdl_f)) for xdl_f in xdl_files]

        # Get schedule
        xdl_schedule = get_schedule(
            xdl_objs,
            graph_f,
            solver_method='random_search',
            generations=30,
        )

        # Check schedule can be saved as XDL, XDLEXE and schedule JSON.
        x = xdl_schedule.to_xdl()
        xdl_schedule.save_xdl(os.path.join(
            OUTPUT_FILES, 'split-graph-addition-scheduled.xdl'))
        # xdl_schedule.save_xdl(os.path.join(
        #     OUTPUT_FILES, 'split-graph-addition-scheduled.xdl'))
        # xdl_schedule.save_xdlexe(os.path.join(
        #     OUTPUT_FILES, 'split-graph-addition-scheduled.xdlexe'))
        xdl_schedule.save_json(
            os.path.join(OUTPUT_FILES, 'split-graph-addition-schedule.json'))

        # Check no waiting is done at the start of any of the async blocks
        unawaited_steps = []
        for step in x.steps:
            if type(step) == Async:
                unawaited_steps.append(step.pid)
                assert type(step.children[0]) != Wait

            elif type(step) == Await:
                unawaited_steps.remove(step.pid)

        # Check all Async steps have a corresponding await
        assert not unawaited_steps

        # Check that all blocks start at T0, as on a split graph there is no
        # reason for them to wait.
        for block in xdl_schedule:
            assert block.start_time == 0

@pytest.mark.unit
def test_staggered_start_scheduling():
    """Test that the situation where the graph is effectively split down the
    middle and a different XDL is ran on each side works.
    """
    # Go through all tests
    for xdl_files, graph_f in STAGGERED_START_TESTS:
        graph_f = os.path.join(FILES, graph_f)

        # Instantiate XDL objects
        xdl_objs = [XDL(os.path.join(FILES, xdl_f)) for xdl_f in xdl_files]

        # Get schedule
        xdl_schedule = get_schedule(
            xdl_objs,
            graph_f,
            solver_method='random_search',
            generations=100,
        )

        # Check schedule can be saved as XDL
        x = xdl_schedule.to_xdl()
        x.save(os.path.join(OUTPUT_FILES, 'staggered-addition-scheduled.xdl'))
        xdl_schedule.save_json(
            os.path.join(OUTPUT_FILES, 'staggered-addition-schedule.json'))

        last_start_time = -1
        for block in xdl_schedule.blocks:
            assert block.start_time > last_start_time
            last_start_time = block.start_time

@pytest.mark.special
def test_scheduling_algorithms_timing():
    """Code for testing timing of different search algorithms. Not a unit test,
    only for special occasions.
    """
    graphs = [
        ('two-reactors', 2, TWO_REACTORS_GRAPH_F),
        ('three-reactors', 3, THREE_REACTORS_GRAPH_F),
        ('four-reactors', 4, FOUR_REACTORS_GRAPH_F)
    ]

    algorithms = (
        # ('grid_search', None),
        # ('random_search', 10),
        ('genetic_algorithm', 10),
    )

    results = {algorithm: [] for algorithm, _ in algorithms}

    for algorithm, generations in algorithms:
        print(f'Testing: {algorithm}')
        for graph_name, n_reactors, graph in graphs:
            print(f'Testing: {graph}')
            graph_f = os.path.join(FILES, graph)

            # Instantiate XDL objects
            xdl_objs = [
                XDL(os.path.join(FILES, TRIFLUOROMETHYLATION_XDL))
                for _ in range(n_reactors)
            ]

            start_t = time.time()
            # Get schedule
            xdl_schedule = get_schedule(
                xdl_objs,
                graph_f,
                solver_method=algorithm,
                generations=generations,
                population_size=1,
                device_modules=[chemputer_devices],
            )
            end_t = time.time()
            results[algorithm].append({
                'graph': graph_name,
                'time': end_t - start_t,
                'makespan': xdl_schedule.makespan
            })
            with open(
                os.path.join(
                    HERE, 'test_output', 'algorithm-timing.json'), 'w') as fd:

                json.dump(results, fd, indent=2)
