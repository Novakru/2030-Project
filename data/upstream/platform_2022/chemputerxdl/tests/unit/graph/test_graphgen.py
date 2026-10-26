import os
import pytest
from xdl import XDL
from xdl.constants import INERT_GAS_SYNONYMS
from xdl.utils.graph import undirected_neighbors
from chemputerxdl.constants import (
    CHILLER_CLASSES,
    FILTER_CLASSES,
    REACTOR_CLASSES,
    ROTAVAP_CLASSES,
    SEPARATOR_CLASSES,
    CHEMPUTER_CARTRIDGE,
    CHEMPUTER_FLASK
)
from chemputerxdl.utils.execution import get_backbone
from ...utils import generic_chempiler_test

HERE = os.path.abspath(os.path.dirname(__file__))
FILES = os.path.join(HERE, 'files')
GLOBAL_FILES = os.path.join(HERE, '..', 'files')
OUTPUT_FILES = os.path.join(HERE, '..', 'test_output')
os.makedirs(OUTPUT_FILES, exist_ok=True)

GRAPHGEN_TESTS = [
    ('orgsyn_v81p0262.xdl'),
    ('orgsyn_v80p0129.xdl'),
    ('orgsyn_v87p0016.xdl'),
    ('orgsyn_v83p0193.xdl'),
]

TEST_FILES = os.path.dirname(HERE)
ROOT_FILES = os.path.join(os.path.dirname(TEST_FILES), "..", "..")

@pytest.mark.unit
def test_graphgen():
    for xdl_f in GRAPHGEN_TESTS:
        x = XDL(os.path.join(FILES, xdl_f))
        save_path = os.path.join(OUTPUT_FILES, xdl_f.split('.')[0] + '.json')
        x.graph(save=save_path)
        print('\n')
        generic_chempiler_test(os.path.join(FILES, xdl_f), save_path)

@pytest.mark.unit
def test_graphgen_reactor_needing_chiller():
    # Reactor requires active cooling
    x = XDL(os.path.join(FILES, 'graphgen_reactor_needing_chiller.xdl'))
    save_path = os.path.join(
        OUTPUT_FILES, 'graphgen_reactor_needing_chiller.json')
    graph = x.graph(auto_fix_issues=True, save=save_path)

    # Check chiller added to reactor
    has_chiller = False
    for _, data in undirected_neighbors(graph, 'reactor', data=True):
        if data['class'] in CHILLER_CLASSES:
            has_chiller = True
            break
    assert has_chiller

    # Reactor requires less than RT
    x = XDL(os.path.join(FILES, 'graphgen_reactor_needing_chiller2.xdl'))
    save_path = os.path.join(
        OUTPUT_FILES, 'graphgen_reactor_needing_chiller2.json')
    graph = x.graph(auto_fix_issues=True, save=save_path)

    # Check chiller added to reactor
    has_chiller = False
    for _, data in undirected_neighbors(graph, 'reactor', data=True):
        if data['class'] in CHILLER_CLASSES:
            has_chiller = True
            break
    assert has_chiller

@pytest.mark.unit
def test_graphgen_use_existing_reagent_flasks():
    x = XDL(os.path.join(FILES, 'graphgen_use_existing_flasks.xdl'))
    save_path = os.path.join(
        OUTPUT_FILES, 'graphgen_use_existing_flasks.json')
    graph = x.graph(
        os.path.join(
            FILES, 'graphgen_use_existing_flasks_template.json'),
        auto_fix_issues=True,
        save=save_path
    )
    cartridges, buffer_flasks, reagent_flasks = [], [], []
    for node, data in graph.nodes(data=True):
        if data['class'] == CHEMPUTER_FLASK:
            chemical = data['chemical']
            if data['chemical']:
                if chemical not in INERT_GAS_SYNONYMS:
                    reagent_flasks.append(data['chemical'])
            else:
                buffer_flasks.append(node)

        elif data['class'] == CHEMPUTER_CARTRIDGE:
            cartridges.append(data['chemical'])

    for reagent in x.reagents:
        reagent_flasks.remove(reagent.name)

    assert len(reagent_flasks) == 0
    assert len(buffer_flasks) == 2
    assert len(cartridges) == 1
    assert cartridges[0] == 'anhydrous magnesium sulfate(MgSO4)'

@pytest.mark.unit
def test_graphgen_remove_unused_modules():
    x = XDL(os.path.join(GLOBAL_FILES, 'lidocaine.xdl'))
    save_path = os.path.join(OUTPUT_FILES, 'lidocaine_graph.json')
    graph = x.graph(save=save_path)

    # Check graph has filter with chiller and separator
    has_filter = False
    has_separator = False
    filter_has_chiller = False
    has_rotavap = False
    has_reactor = False

    for node, data in graph.nodes(data=True):
        if data['class'] in FILTER_CLASSES:
            has_filter = True
            for _, neighbor_data in undirected_neighbors(
                    graph, node, data=True):
                if neighbor_data['class'] in CHILLER_CLASSES:
                    filter_has_chiller = True

        elif data['class'] in REACTOR_CLASSES:
            has_reactor = True

        elif data['class'] in SEPARATOR_CLASSES:
            has_separator = True

        elif data['class'] in ROTAVAP_CLASSES:
            has_rotavap = True

    assert has_filter
    assert filter_has_chiller
    assert has_separator
    assert not has_rotavap
    assert not has_reactor


OPTIMIZE_FLASK_TESTS = {
    'orgsyn_v81p0262': {
        'flask_distilled water': 0,
        'flask_hexanes': 0,
        'flask_toluene': 1,
        'flask_benzylamine': [0, 2]
    },
    'orgsyn_v80p0129': {
        'flask_distilled water': 0,
        'flask_propiolic acid': 1,
        'flask_nitrogen': 0,
        'flask_hydriodic acid': 0,
    },
}

@pytest.mark.unit
def test_graphgen_optimize_flasks():
    # Get expected number of assertions
    expected_n_assertions = len([
        _ for _, expected_pos in OPTIMIZE_FLASK_TESTS.items()
        for _ in expected_pos
    ])

    n_assertions = 0
    # Check flasks are all in the right place
    for xdl_f, expected_positions in OPTIMIZE_FLASK_TESTS.items():
        x = XDL(os.path.join(FILES, xdl_f + '.xdl'))
        graph = x.graph(
            save=os.path.join(OUTPUT_FILES, xdl_f + '_graph.json'))

        backbone = get_backbone(graph, ordered=True)

        for node in graph.nodes():
            if node in expected_positions:
                expected_index = expected_positions[node]

                for neighbor in undirected_neighbors(graph, node):
                    if neighbor in backbone:
                        try:
                            if type(expected_index) == int:
                                assert (
                                    backbone.index(neighbor)
                                    == expected_index
                                )
                            else:
                                assert (
                                    backbone.index(neighbor)
                                    in expected_index
                                )
                        except AssertionError:
                            raise AssertionError(
                                f'File: {xdl_f}\n{node} expected in\
 position {expected_index}, found in position {backbone.index(neighbor)}'
                            )
                        n_assertions += 1

    # Check everything in tests has been asserted
    assert n_assertions == expected_n_assertions

@pytest.mark.unit
def test_graphgen_graph_can_be_used_directly():
    """This is in response to a bug where using the graph as a MultiDiGraph
    object without saving/loading caused weird errors.
    """
    x = XDL(os.path.join(FILES, 'orgsyn_v87p0016.xdl'))
    graph = x.graph()
    x.prepare_for_execution(graph, interactive=False)

@pytest.mark.unit
def test_graphgen_extend_backbone():
    x = XDL(os.path.join(GLOBAL_FILES, 'lidocaine.xdl'))
    graph = x.graph(
        graph_template=os.path.join(FILES, 'two-valve-template.json'),
        save=os.path.join(OUTPUT_FILES, 'extend-backbone.json')
    )
    x.prepare_for_execution(graph, interactive=False)
