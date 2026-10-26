"""
.. module:: steps_synthesis.heatchill
    :platforms: Unix, Windows
    :synopsis: XDL step for adding Heating or Chilling substeps

"""

from typing import Optional, List, Dict, Any
from networkx import MultiDiGraph

# XDL
from xdl.steps.base_steps import Step
from xdl.steps.templates import AbstractHeatChillStep
from xdl.utils.prop_limits import (
    TIME_PROP_LIMIT,
    TEMP_PROP_LIMIT,
    ROTATION_SPEED_PROP_LIMIT,
    HEATCHILL_PURPOSE_PROP_LIMIT,
)
from xdl.constants import VESSEL_PROP_TYPE

# Relative
from ..base_step import ChemputerStep
from ..steps_base import CRotavapLiftDown, CRotavapLiftUp
from ..steps_utility import (
    Wait, HeatChillToTemp, StopHeatChill, StartStir, StopStir)
from ...utils.execution import get_vessel_type

class HeatChill(ChemputerStep, AbstractHeatChillStep):
    """Heat or chill vessel to given temp for given time.

    Args:
        vessel (str): Vessel to heat/chill.
        temp (float): Temperature to heat/chill vessel to in °C.
        time (float): Time to heat/chill vessel for in seconds.
        stir (bool): True if step should be stirred, otherwise False.
        stir_speed (float): Speed to stir at in RPM. Only use if stir is True.
        purpose (str): Optional. Purpose of step. One of 'reaction',
            'control-exotherm' or 'unstable-reagent'.
        vessel_type (str): Given internally. Vessel type so the step knows what
            base steps to use. 'ChemputerFilter' or 'ChemputerReactor'.
    """

    DEFAULT_PROPS = {
        'stir': True,
        'stir_speed': '250 RPM',
        'purpose': None,
    }

    PROP_TYPES = {
        'vessel': VESSEL_PROP_TYPE,
        'temp': float,
        'time': float,
        'stir': bool,
        'stir_speed': float,
        'purpose': str,
        'vessel_type': str,
    }

    INTERNAL_PROPS = [
        'vessel_type',
    ]

    PROP_LIMITS = {
        'temp': TEMP_PROP_LIMIT,
        'time': TIME_PROP_LIMIT,
        'stir_speed': ROTATION_SPEED_PROP_LIMIT,
        'purpose': HEATCHILL_PURPOSE_PROP_LIMIT,
    }

    ALWAYS_WRITE = [
        'stir',
    ]

    def __init__(
        self,
        vessel: str,
        temp: float,
        time: float,
        stir: bool = 'default',
        stir_speed: float = 'default',
        purpose: str = 'default',

        # Internal properties
        vessel_type: Optional[str] = None,
        **kwargs
    ) -> None:
        super().__init__(locals())

    def on_prepare_for_execution(self, graph: MultiDiGraph):
        """Prepares the current step for execution.
        Gets/sets/cleans up appropriate items in preparation for exection.

        Args:
            graph (MultiDiGraph): Chemputer Graph to check
        """

        # Obtain the vessel type if not defined
        if not self.vessel_type:
            self.vessel_type = get_vessel_type(graph, self.vessel)

    def get_steps(self) -> List[Step]:
        """Get the list of steps/base steps to execute.

        Returns:
            List[Step]: Steps to execute.
        """

        steps = [
            # Heat or Chill the vessel
            HeatChillToTemp(
                vessel=self.vessel,
                temp=self.temp,
                stir=self.stir,
                stir_speed=self.stir_speed,
                vessel_type=self.vessel_type
            ),

            # Wait for required time
            Wait(time=self.time),

            # Stop Heating or chilling
            StopHeatChill(vessel=self.vessel, vessel_type=self.vessel_type),
        ]

        # Insert a StartStir step at beginning if stirring required
        if self.stir:
            steps.insert(
                0,
                StartStir(
                    vessel=self.vessel,
                    vessel_type=self.vessel_type,
                    stir_speed=self.stir_speed
                )
            )

        # Add in a StopStir step at beginning if stirring not required
        else:
            steps.insert(
                0,
                StopStir(
                    vessel=self.vessel, vessel_type=self.vessel_type
                )
            )

        # we bracket the steps with liftup/down if it's a rotavap
        if self.vessel_type == 'rotavap':
            steps.insert(0, CRotavapLiftDown('rotavap'))
            steps.append(CRotavapLiftUp('rotavap'))
        return steps

    @property
    def requirements(self) -> Dict[str, Dict[str, Any]]:
        """Get the requirements needed for this step

        Returns:
            Dict[str, Dict[str, Any]]: Step requirements
        """

        return {
            'vessel': {
                'heatchill': True,
                'temp': [self.temp],
            }
        }
