import os
import pytest
from xdl import XDL
from chemputerxdl.graphgen.get_graph_spec import get_graph_spec

HERE = os.path.abspath(os.path.dirname(__file__))
FILES = os.path.join(HERE, 'files')

GET_GRAPH_SPEC_TESTS = [
    ('orgsyn_v83p0193.xdl', {
        'reagents': [
            '2 methylcyclohexanone',
            'triethylamine',
            'sodium iodide acetonitrile solution',
            'saturated sodium bicarbonate solution',
            'hexane',
            'brine',
        ],
        'buffer_flasks': [
            {'n_required': 2, 'connected_node': 'separator'},
            {'n_required': 1, 'connected_node': 'separator'},  # in safe_mode
        ],
        'cartridges': [
            {'from': 'rotavap', 'to': 'reactor', 'chemical': 'silica-gel'},
            {'from': 'separator', 'to': 'rotavap', 'chemical': 'MgSO4'}
        ],
        'vessels': {
            'types': [
                ('rotavap', 'rotavap'),
                ('reactor', 'reactor'),
                ('separator', 'separator')
            ],
            'temps': {
                'rotavap': [30],
                'reactor': [50],
            }
        }
    })
]

@pytest.mark.unit
def test_get_graph_spec():
    """Test that graph generation from template works."""
    for test_xdl_f, test_info in GET_GRAPH_SPEC_TESTS:
        x = XDL(os.path.join(FILES, test_xdl_f))
        graph_spec = get_graph_spec(x)
        test_graph_spec_reagents(test_info['reagents'], graph_spec['reagents'])
        test_graph_spec_buffer_flasks(
            test_info['buffer_flasks'], graph_spec['buffer_flasks'])
        test_graph_spec_cartridges(
            test_info['cartridges'], graph_spec['cartridges'])
        test_graph_spec_vessels(test_info['vessels'], graph_spec['vessels'])


def test_graph_spec_reagents(correct_reagent, graph_spec_reagents):
    graph_spec_reagents = set(graph_spec_reagents)
    assert len(graph_spec_reagents) == len(correct_reagent)
    for reagent in correct_reagent:
        assert reagent in graph_spec_reagents

def test_graph_spec_buffer_flasks(
        correct_buffer_flasks, graph_spec_buffer_flasks):
    assert len(correct_buffer_flasks) == len(graph_spec_buffer_flasks)
    for buffer_flask in correct_buffer_flasks:
        found = False
        for graph_spec_buffer_flask in graph_spec_buffer_flasks:
            print(graph_spec_buffer_flask)
            if (buffer_flask['n_required']
                == graph_spec_buffer_flask['n_required']
                and buffer_flask['connected_node']
                    == graph_spec_buffer_flask['connected_node']):
                found = True
        assert found

def test_graph_spec_cartridges(correct_cartridges, graph_spec_cartridges):
    assert len(correct_cartridges) == len(graph_spec_cartridges)
    for cartridge in correct_cartridges:
        found = False
        for graph_spec_cartridge in graph_spec_cartridges:
            if (cartridge['from'] == graph_spec_cartridge['from']
                and cartridge['to'] == graph_spec_cartridge['to']
                and cartridge['chemical']
                    == graph_spec_cartridge['chemical']):
                found = True
        assert found

def test_graph_spec_vessels(correct_vessels, graph_spec_vessels):
    assert len(correct_vessels['types']) == len(graph_spec_vessels['types'])
    for component_type in correct_vessels['types']:
        assert component_type in graph_spec_vessels['types']
    assert len(graph_spec_vessels['temps']) == len(correct_vessels['temps'])
    for vessel, temps in correct_vessels['temps'].items():
        graph_spec_temps = [
            temp.temp for temp in graph_spec_vessels['temps'][vessel]]
        assert len(temps) == len(graph_spec_vessels['temps'][vessel])
        for temp in temps:
            assert temp in graph_spec_temps
