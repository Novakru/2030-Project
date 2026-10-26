"""
Chemputer Execution Client
--------------------------
This file launches a Chemputer execution client that can be used for physically
executing procedures from ChemIDE. To use, run this file
`python execution-client.py`, and then paste the execution key printed to the
terminal into the execution key input in ChemIDE and click "Connect".
"""
import argparse
from chemputerxdl.execution_client import ChemputerExecutionClient

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--test', action='store_true')
    parser.add_argument('--simulation', action='store_true')
    args = parser.parse_args()

    # Instantiate client
    if args.test:
        client = ChemputerExecutionClient(
            'http://localhost:5000', simulation=args.simulation)
    else:
        client = ChemputerExecutionClient(
            'https://api.chemification.com', simulation=args.simulation)

    # Run client
    client.run()
