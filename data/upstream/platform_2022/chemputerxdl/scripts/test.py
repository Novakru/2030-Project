from chempiler import Chempiler
import ChemputerAPI
import argparse
import os
from xdl import XDL

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('xdl_file', type=str)
    parser.add_argument('graph_file', type=str)
    parser.add_argument('--interactive', action='store_true')
    args = parser.parse_args()

    if not os.path.exists(args.xdl_file):
        raise FileNotFoundError(f"Can't find xdl file '{args.xdl_file}'.")

    if not os.path.exists(args.graph_file):
        raise FileNotFoundError(f"Can't find graph file '{args.graph_file}'.")

    x = XDL(args.xdl_file)
    x.prepare_for_execution(args.graph_file, interactive=args.interactive)

    c = Chempiler(
        experiment_code='test',
        output_dir='.',
        graph_file=args.graph_file,
        simulation=True,
        device_modules=[ChemputerAPI],
    )

    x.execute(c)


if __name__ == '__main__':
    main()
