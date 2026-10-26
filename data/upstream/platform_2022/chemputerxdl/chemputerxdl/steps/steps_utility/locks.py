"""
.. module:: steps_utility.locks
    :platforms: Unix, Windows
    :synopsis: Handling the (un)locking of XDLLocks for parallelization.

"""

import ast
from typing import List, Union
from xdl.steps.base_steps import AbstractBaseStep

from ..base_step import ChemputerStep


class Unlock(ChemputerStep, AbstractBaseStep):
    """
    A basestep to unlock a list of given nodes.
    If "all" nodes, all nodes held by a given pid will be unlocked.

    Args:
        nodes (Union[List, str]): Nodes to unlock. List or "all".
        pid (str): Process ID must be given if using nodes="all".
    """

    PROP_TYPES = dict(
        nodes=Union[List, str],
        pid=str,
    )

    def __init__(self, pid=None, nodes=None, **kwargs):
        super().__init__(locals())

    def execute(self, platform_controller, *args, **kwargs):
        return True

    def locks(self, platform_controller):
        """
        Returns list of given nodes or list of all nodes held by given pid.
        """
        unlocks = []
        if self.nodes == "all" and self.pid is not None:
            for node in platform_controller.graph.nodes:
                lock = platform_controller.graph[node]["xdl_locks"]['ongoing']
                if lock.pid == self.pid:
                    unlocks.append(node)

        elif isinstance(self.nodes, list):
            unlocks = self.nodes

        elif isinstance(self.nodes, str):
            unlocks = ast.literal_eval(self.nodes)
            assert isinstance(unlocks, list)

        else:
            raise Exception(
                "Nodes not recognized as list or valid string.", self.nodes)

        return [], [], unlocks
