import os
import sys
import stat
from typing import Callable, List, Optional, Union
from networkx.classes.multidigraph import MultiDiGraph
import pytest
import shutil
from xdl import XDL
from xdl.utils.graph import get_graph
from xdl.steps import Step, AbstractBaseStep, UnimplementedStep
from xdl.readwrite.xml_generator import step_to_xml_string
from chempiler import Chempiler
import ChemputerAPI
import commanduinolabware
from chemputerxdl.executor import ChemputerExecutor

HERE = os.path.abspath(os.path.dirname(__file__))

def _error_handler(func, path, exc_info):
    """
    Error handler for error caused by ``shutil.rmtree``.

    If the error is due to an access error (read only file)
    it attempts to add write permission and then retries.
    Otherwise, it re-raises the error.

    Usage : ``shutil.rmtree(path, onerror=_error_handler)``
    Adapted from StackOverflow solution:
    ```https://stackoverflow.com/questions/2656322/
            shutil-rmtree-fails-on-windows-with-access-is-denied```
    """
    if not os.access(path, os.W_OK):
        # Is the error an access error ?
        os.chmod(path, stat.S_IWUSR)
        func(path)

def get_chempiler(graph_file: str) -> Chempiler:
    path = os.path.join(HERE, 'chempiler_output')
    if os.path.isdir(path):
        shutil.rmtree(path, onerror=_error_handler)

    return Chempiler(
        experiment_code='test',
        output_dir=path,
        simulation=True,
        graph_file=graph_file,
        device_modules=[ChemputerAPI, commanduinolabware]
    )


def generic_chempiler_test(xdl_file: str, graph_file: str) -> None:
    """Given XDL file and graph file, try and execute Chempiler simulation
    of XDL.

    Args:
        xdl_file (str): Path to XDL file.
        graph_file (str): Path to graph file.
    """
    x = XDL(xdl_file)
    for i in reversed(range(len(x.steps))):
        if isinstance(x.steps[i], UnimplementedStep):
            x.steps.pop(i)
    x.prepare_for_execution(graph_file, testing=True)
    x.steps = [
        remove_confirm_steps(step) for step in x.steps]
    old_stdout = sys.stdout
    with open(os.devnull, 'w') as devnull:
        sys.stdout = devnull
        chempiler = get_chempiler(graph_file)
        x.execute(chempiler)
    sys.stdout = old_stdout

def remove_confirm_steps(step: Step) -> None:
    """Recursively remove Confirm steps from given step, going all the way down
    step tree. This needs to be done as you can't ask for input during an
    automated test.

    Args:
        step (Step): Step to remove Confirm steps from.
    """
    # If step is base step just return step.
    if isinstance(step, AbstractBaseStep):
        return step
    else:
        for i in reversed(range(len(step.steps))):
            if step.steps[i].name == 'Confirm':
                step.steps.pop(i)
            else:
                step.steps[i] = remove_confirm_steps(step.steps[i])
        return step

def test_step(step, correct_step_info):
    assert type(step) == correct_step_info[0]
    for k, v in correct_step_info[1].items():
        assert k in step.properties
        assert step.properties[k] == v

class XDLTestError(Exception):
    pass

class XDLStoryMissingSubstepError(XDLTestError):
    """Raised when substeps specified in XDLStory aren't found in step substep
    tree.
    """
    def __init__(self, substep):
        self.substep = substep

    def __str__(self):
        s = 'Unable to find the following substep:\n'
        if type(self.substep) == type:
            s += f'{self.substep.__name__}'
        else:
            s += f'{self.substep.name} {self.substep.properties}\n'
        return s

class XDLStoryInvalidSubstepError(XDLTestError):
    """Raised when substeps specified in XDLStory aren't found in step substep
    tree.
    """
    def __init__(self, substep):
        self.substep = substep

    def __str__(self):
        s = 'Following invalid substep found in step tree:\n'
        if type(self.substep) == type:
            s += f'{self.substep.__name__}'
        else:
            s += f'{self.substep.name} {self.substep.properties}\n'
        return s

def run_xdl_story(
    start: Step,
    substeps: Optional[List[Union[Step, type]]] = None,
    not_substeps: Optional[List[Union[Step, type]]] = None,
    graph: Optional[Union[str, MultiDiGraph]] = None,
    compile: bool = True,
    sanity_check: bool = True,
    execute: bool = True,
    save: str = None,
):
    """Runs XDL story according to given parameters

    Args:
        start (AbstractStep): Step to instantiate and test.
        substeps (Optional[List[Union[Step, type]]]): List of substeps that
            should be found in ``start`` step tree. Substeps can be types
            or step objects to match properties as well. Order doesn't matter.
        not_substeps (Optional[List[Union[Step, type]]]): List of substeps that
            should not be found in ``start`` step tree. Substeps can be types
            or step objects to match properties as well. Order doesn't matter.
        graph (Optional[Union[str, MultiDiGraph]]): Graph to use for compilation
            and execution.
        compile (bool): If ``True`` compile step during test.
        sanity_check (bool): If ``True`` run step sanity checks during test.
        execute (bool): If ``True`` execute step during test.
        mark (Callable): Pytest mark to decorate test function with.

    Returns:
        Callable: Test function that runs story according to given parameters
    """
    substeps = substeps or []
    not_substeps = not_substeps or []

    if compile:
        graph = get_graph(graph)
        xdl_executor = ChemputerExecutor()
        xdl_executor.add_internal_properties_to_step(graph=graph, step=start)
        for substep in substeps:
            xdl_executor.add_internal_properties_to_step(
                graph=graph, step=substep)

    # Save full XML step tree to file
    if save:
        with open(save, 'w') as fd:
            fd.write(
                step_to_xml_string(start, full_properties=True, full_tree=True))

    if sanity_check:
        xdl_executor.perform_sanity_checks(graph=graph, steps=[start])

    if substeps or not_substeps:
        for step in start.step_tree:
            # Check for substeps that should be there
            if substeps:
                substep = substeps[0]
                match = False

                # Match by step type
                if type(substep) == type and substep == type(step):
                    match = True

                # Match by step object
                elif isinstance(substep, Step) and substep == step:
                    match = True

                if match:
                    substeps.pop(0)

            # Check for substeps that shouldn't be there
            for i in reversed(range(len(not_substeps))):

                not_substep = not_substeps[i]

                # Check by step type
                if type(not_substep) == type and type(step) == not_substep:
                    raise XDLStoryInvalidSubstepError(not_substep)

                # Check by step obejct
                elif isinstance(not_substep, Step) and not_substep == step:
                    raise XDLStoryInvalidSubstepError(not_substep)

        if substeps:
            raise XDLStoryMissingSubstepError(substeps[0])

    if execute:
        platform_controller = get_chempiler(graph)
        xdl_executor.execute_step(platform_controller, start)

def XDLStory(
    name: str,
    start: Step,
    substeps: Optional[List[Step]] = None,
    not_substeps: Optional[List[Union[Step, type]]] = None,
    error: Optional[Exception] = None,
    graph: Optional[Union[str, MultiDiGraph]] = None,
    compile: bool = True,
    sanity_check: bool = True,
    execute: bool = True,
    mark: Callable = None,
    save: str = None,
) -> Callable:
    """Returns a test function. The idea is that steps can be easily tested for
    generally working and having certain substeps. E.g.

    ``test_story = XDLStory(
        start=StartStir(vessel='reactor'),
        substeps=[CStirringControllerStart(vessel='reactor')],
        graph='test_graph.json'
    )``

    Args:
        name (str): Name of test. Should describe clearly the scenario
            presented in the ``start`` step.
        start (AbstractStep): Step to instantiate and test.
        substeps (Optional[List[Union[Step, type]]]): List of substeps that
            should be found in ``start`` step tree. Substeps can be types
            or step objects to match properties as well. Order doesn't matter.
        not_substeps (Optional[List[Union[Step, type]]]): List of substeps that
            should not be found in ``start`` step tree. Substeps can be types
            or step objects to match properties as well. Order doesn't matter.
        error (Optional[Exception]): Error type that should be thrown during
            story. If ``None``, expect no error to be thrown.
        graph (Optional[Union[str, MultiDiGraph]]): Graph to use for compilation
            and execution.
        compile (bool): If ``True`` compile step during test.
        sanity_check (bool): If ``True`` run step sanity checks during test.
        execute (bool): If ``True`` execute step during test.
        mark (Callable): Pytest mark to decorate test function with.
        save (str): File path to save step tree to for debugging

    Returns:
        Callable: Test function that runs story according to given parameters
    """
    @mark
    def test():
        print(f'Testing XDL Story: {name}')
        if not error:
            run_xdl_story(
                start=start,
                substeps=substeps,
                not_substeps=not_substeps,
                graph=graph,
                compile=compile,
                sanity_check=sanity_check,
                execute=execute,
                save=save
            )
        else:
            with pytest.raises(error):
                run_xdl_story(
                    start=start,
                    substeps=substeps,
                    not_substeps=not_substeps,
                    graph=graph,
                    compile=compile,
                    sanity_check=sanity_check,
                    execute=execute,
                    save=save
                )
    return test
