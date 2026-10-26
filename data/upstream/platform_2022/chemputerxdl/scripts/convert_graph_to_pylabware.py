import json
import sys
import os

class_mappings = {
    'IKARV10': 'R300Rotovap',
    'JULABOCF41': 'CF41Chiller',
    'CVC3000': 'CVC3000VacuumPump',
    'C3000': 'C3000SyringePump',
    'IKARETControlVisc': 'RETControlViscHotplate',
    'IKARCTDigital': 'RCTDigitalHotplate',
    'IKAmicrostar75': 'Microstar75Stirrer',
    'Huber': 'PetiteFleurChiller',
    'RZR_2052': 'RZR2052ControlStirrer',
    'HeiTORQUE_100': 'HeiTorque100PrecisionStirrer',
}

property_mappings = {
    'mode': 'connection_mode',
}

value_mappings = {
    'connection_mode': {
        'ethernet': 'tcpip',
    }
}

def convert_dir_to_pylabware(dirname):
    """Convert directory to PyLabware graphs."""
    # Go through directory
    for f in os.listdir(dirname):
        f_path = os.path.join(dirname, f)

        # Is .json file, convert to PyLabware graph
        if f.endswith('.json'):
            convert_graph_to_pylabware(f_path)

        # Is directory, recursively convert to PyLabware graphs
        elif os.path.isdir(f_path):
            convert_dir_to_pylabware(f_path)

def convert_graph_to_pylabware(graph_file):
    """Convert graph to PyLabware graph. Safe to call this on graph that has
    already been converted.
    """
    # Load graph
    with open(graph_file) as fd:
        graph = json.load(fd)

    # Go through nodes and apply all necessary changes
    for i, node in enumerate(graph['nodes']):

        # Apply class mappings
        if node['class'] in class_mappings:
            node['class'] = class_mappings[node['class']]

        # Apply property mappings
        new_props = {}
        for k, v in node.items():
            if k in property_mappings:
                new_props[property_mappings[k]] = v
            else:
                new_props[k] = v

            # Apply value mappings
            if k in value_mappings:
                if v in value_mappings[k]:
                    new_props[k] = value_mappings[k][v]

        graph['nodes'][i] = new_props

    # Save updated graph
    with open(graph_file, 'w') as fd:
        json.dump(graph, fd, indent=2)


if __name__ == '__main__':
    # Convert all .json files in directory to PyLabware graph
    if os.path.isdir(sys.argv[1]):
        convert_dir_to_pylabware(sys.argv[1])

    # Convert one file to PyLabware graph
    else:
        convert_graph_to_pylabware(sys.argv[1])
