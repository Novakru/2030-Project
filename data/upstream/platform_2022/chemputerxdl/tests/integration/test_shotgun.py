# import pytest
import os
import logging

from xdl import XDL
from xdl.errors import XDLError
from chemputerxdl.utils.execution import get_chempiler

from ..utils import remove_confirm_steps

HERE = os.path.abspath(os.path.dirname(__file__))
FILES_FOLDER = os.path.join(HERE, 'files')

# @pytest.mark.integration
def test_shotgun():
    """Try to generate graph, compile and execute a big bunch of XDL files and
    print the error rate, and proportion of non XDLError exceptions.
    """
    caught, uncaught, success = 0, 0, 0
    files = [f for f in os.listdir(FILES_FOLDER) if f.endswith('.xdl')]
    for f in files:
        f_path = os.path.join(FILES_FOLDER, f)
        try:
            test_file(f_path)
            success += 1
        except XDLError:
            caught += 1
        except Exception as e:
            raise e
            uncaught += 1
    errors = caught + uncaught
    print(
        f'Tested: {success + caught + uncaught}  Error rate: {errors / len(files):.2f}\nCaught: {caught / errors:.2f}'
    )

def test_file(f):
    print(f'Testing file: {f}')
    x = XDL(f)
    graph_file = f[:-3] + 'json'
    x.graph(save=graph_file)
    x.prepare_for_execution(graph_file, testing=True)
    x.steps = [
        remove_confirm_steps(step)
        for step in x.steps
        if step.name != 'Confirm'
    ]
    c = get_chempiler(graph_file)
    logging.getLogger('chempiler').setLevel(logging.CRITICAL)
    x.execute(c)
    os.remove(graph_file)
    os.remove(f + 'exe')
