"""
.. module:: steps_utility.standby
    :platforms: Unix, Windows
    :synopsis: XDL step to periodically clean the system when not in use.

"""

from typing import Optional, List
from networkx import MultiDiGraph

# XDL
from xdl.steps import AbstractStep
from xdl.steps.base_steps import Step
from xdl.steps.special_steps import Loop
from xdl.utils.misc import SanityCheck
from xdl.utils.prop_limits import TIME_PROP_LIMIT
from xdl.constants import REAGENT_PROP_TYPE

# Relative
from .general import Wait
from .cleaning import CleanBackbone
from ..base_step import ChemputerStep

class Standby(ChemputerStep, AbstractStep):
    """Move solvent around once every specified time interval to prevent
    sticking of valves and pumps. Continues indefinitely.

    Args:
        solvent (str): Solvent with which to clean
        time_interval (str): Activate periodically after this many hours.
    """

    PROP_TYPES = {
        'solvent': REAGENT_PROP_TYPE,
        'time_interval': float
    }

    PROP_LIMITS = {
        'time_interval': TIME_PROP_LIMIT,
    }

    DEFAULT_PROPS = {
        'time_interval': '24 hrs',
    }

    def __init__(
        self,
        solvent: str,
        time_interval: Optional[float] = 'default',
        **kwargs
    ):
        super().__init__(locals())

    def get_steps(self) -> List[Step]:
        """Get the list of steps/base steps to execute.

        Returns:
            List[Step]: Steps to execute.
        """

        # Wait until the end of a time interval before cleaning
        loop_steps = [
            Wait(time=self.time_interval),
            CleanBackbone(solvent=self.solvent)
        ]

        # Loop steps
        return [Loop(loop_steps)]

    def sanity_checks(self, graph: MultiDiGraph) -> List[SanityCheck]:
        """Gets a list of Sanity checks to perform for the step

        Args:
            graph (MultiDiGraph): Chemputer graph to check

        Returns:
            List[SanityCheck]: List of checks to perform
        """

        return [
            SanityCheck(
                condition=self.time_interval >= 3600.0,
                error_msg='Please specify standby time interval of at least 1\
 hour.',
            )
        ]
