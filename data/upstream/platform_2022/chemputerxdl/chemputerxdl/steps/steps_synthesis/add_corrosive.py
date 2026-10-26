"""
.. module:: steps_synthesis.add_corrosive
    :platforms: Unix, Windows
    :synopsis: Step for adding corrosive compounds

"""

from typing import Optional, List
from networkx import MultiDiGraph

# XDL
from xdl.steps.base_steps import Step, AbstractStep
from xdl.utils.prop_limits import VOLUME_PROP_LIMIT
from xdl.constants import REAGENT_PROP_TYPE, VESSEL_PROP_TYPE

# Relative
from ..base_step import ChemputerStep
from ..steps_utility import Transfer, StartStir, StopStir
from ...utils.execution import get_reagent_vessel

class AddCorrosive(ChemputerStep, AbstractStep):
    """Add corrosive reagent that can't come into contact with a valve.

    Args:
        reagent (str): Reagent to add.
        vessel (str): Vessel to add reagent to.
        volume (float): Volume of reagent to add.
        reagent_vessel (str): Used internally. Vessel containing reagent.
        air_vessel (str): Used internally. Vessel containing air.
    """

    PROP_TYPES = {
        'reagent': REAGENT_PROP_TYPE,
        'vessel': VESSEL_PROP_TYPE,
        'volume': float,
        'stir': bool,
        'reagent_vessel': str,
        'air_vessel': str
    }

    DEFAULT_PROPS = {
        'stir': True,
    }

    INTERNAL_PROPS = [
        'reagent_vessel',
        'air_vessel',
    ]

    PROP_LIMITS = {
        'volume': VOLUME_PROP_LIMIT,
    }

    def __init__(
        self,
        reagent: str,
        vessel: str,
        volume: float,
        stir: Optional[bool] = 'default',

        # Internal properties
        reagent_vessel: Optional[str] = None,
        air_vessel: Optional[str] = None,
        **kwargs
    ) -> None:
        super().__init__(locals())

    def on_prepare_for_execution(self, graph: MultiDiGraph):
        """Prepares the current step for execution.
        Gets/sets/cleans up appropriate items in preparation for exection.

        Args:
            graph (MultiDiGraph): Chemputer Graph to check
        """

        # No reagent vesesl is defined
        if not self.reagent_vessel:
            # Get the reagent vessel
            self.reagent_vessel = get_reagent_vessel(graph, self.reagent)

    def get_steps(self) -> List[Step]:
        """Get the list of steps/base steps to execute.

        Returns:
            List[Step]: Steps to execute.
        """

        # Add appropriate steps
        steps = [
            Transfer(
                from_vessel=self.air_vessel,
                to_vessel=self.vessel,
                through=self.reagent_vessel,
                volume=self.volume
            )
        ]

        # Stirring is set, add Stirring step to beginning of list
        if self.stir:
            steps.insert(0, StartStir(vessel=self.vessel))

        # Stirring is not set, add in a StopStirring step at the beginning.
        else:
            steps.insert(0, StopStir(vessel=self.vessel))

        # Return list of steps
        return steps
