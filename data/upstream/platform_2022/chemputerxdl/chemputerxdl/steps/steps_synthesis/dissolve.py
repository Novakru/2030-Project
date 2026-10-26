"""
.. module:: steps_synthesis.dissolve
    :platforms: Unix, Windows
    :synopsis: XDL step for dissolving a material in a flask or rotavap

"""

from typing import Optional, List, Dict, Any
from networkx import MultiDiGraph

# XDL
from xdl.steps.base_steps import Step
from xdl.steps.templates import AbstractDissolveStep
from xdl.utils.prop_limits import (
    TIME_PROP_LIMIT,
    TEMP_PROP_LIMIT,
    VOLUME_PROP_LIMIT,
    ROTATION_SPEED_PROP_LIMIT,
)
from xdl.constants import VESSEL_PROP_TYPE, REAGENT_PROP_TYPE

# Relative
from .add import Add
from ..base_step import ChemputerStep
from ..steps_utility import (
    Wait,
    HeatChillToTemp,
    StopHeatChill,
)
from ..steps_base import (
    CRotavapLiftDown,
    CRotavapLiftUp,
)
from ...constants import PORT_PROP_TYPE, MAX_ROTAVAP_STIR_SPEED
from ...utils.execution import get_vessel_type
from ...utils.prop_limits import VESSEL_TYPE_PROP_LIMIT, PORT_PROP_LIMIT

class Dissolve(ChemputerStep, AbstractDissolveStep):
    """Dissolve contents of vessel in given solvent.

    Args:
        vessel (str): Vessel to dissolve contents of.
        solvent (str): Solvent to dissolve contents of vessel with.
        volume (float): Volume of solvent to use.
        port (str): Port to add solvent to.
        move_speed (float): Speed in mL / min to move liquid at. (optional)
        aspiration_speed (float): Aspiration speed (speed at which liquid is
            pulled out of reagent_vessel).
        dispense_speed (float): Dispense speed (speed at which liquid is pushed
            from pump into vessel).
        temp (float): Temperature to stir at. Optional.
        time (float): Time to stir for. Optional.
        stir_speed (float): Speed to stir at in RPM.
        solvent_vessel (str): Given internally. Flask containing solvent.
        vessel_type (str): Given internally. 'reactor', 'filter', 'rotavap',
            'flask' or 'separator'.
    """

    DEFAULT_PROPS = {
        'time': '20 minutes',
        'temp': '25°C',
        'stir_speed': '400 RPM',
        'port': None,
        'move_speed': 40,  # mL / min
        'aspiration_speed': 40,  # mL / min
        'dispense_speed': 40,  # mL / min
    }

    PROP_TYPES = {
        'vessel': VESSEL_PROP_TYPE,
        'solvent': REAGENT_PROP_TYPE,
        'volume': float,
        'port': PORT_PROP_TYPE,
        'temp': float,
        'time': float,
        'stir_speed': float,
        'vessel_type': str,
        'move_speed': float,
        'aspiration_speed': float,
        'dispense_speed': float,
    }

    INTERNAL_PROPS = [
        'vessel_type',
    ]

    PROP_LIMITS = {
        'volume': VOLUME_PROP_LIMIT,
        'port': PORT_PROP_LIMIT,
        'temp': TEMP_PROP_LIMIT,
        'time': TIME_PROP_LIMIT,
        'stir_speed': ROTATION_SPEED_PROP_LIMIT,
        'vessel_type': VESSEL_TYPE_PROP_LIMIT,
    }

    def __init__(
        self,
        vessel: str,
        solvent: str,
        volume: float,
        port: Optional[str] = 'default',
        temp: Optional[float] = 'default',
        time: Optional[float] = 'default',
        stir_speed: Optional[float] = 'default',
        move_speed: Optional[float] = 'default',
        aspiration_speed: Optional[float] = 'default',
        dispense_speed: Optional[float] = 'default',

        # Internal properties
        vessel_type: Optional[str] = None,
        **kwargs,
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

        # If using rotavap, check stir speed doesn't exceed max rotavap stir
        # speed
        if self.vessel_type == 'rotavap':
            self.stir_speed = min(self.stir_speed, MAX_ROTAVAP_STIR_SPEED)

    def get_steps(self) -> List[Step]:
        """Get the list of steps/base steps to execute.

        Returns:
            List[Step]: Steps to execute.
        """
        steps = [
            Add(
                reagent=self.solvent,
                volume=self.volume,
                vessel=self.vessel,
                port=self.port,
                move_speed=self.move_speed,
                aspiration_speed=self.aspiration_speed,
                dispense_speed=self.dispense_speed,
            ),
            HeatChillToTemp(
                vessel=self.vessel,
                temp=self.temp,
                stir=True,
                stir_speed=self.stir_speed
            ),
            Wait(self.time),
            StopHeatChill(vessel=self.vessel),
        ]

        # Lift arm down and up at start and end if dissolving in rotavap
        if self.vessel_type == 'rotavap':
            steps.insert(0, CRotavapLiftDown(self.vessel))
            steps.append(CRotavapLiftUp(self.vessel))

        return steps

    @property
    def requirements(self) -> Dict[str, Dict[str, Any]]:
        """Gets the requirements needed for this step.

        Returns:
            Dict[str, Dict[str, Any]]: Requirements for the step.
        """

        return {
            'vessel': {
                'heatchill': True,
                'temp': [self.temp],
                'stir': True,
            }
        }

    def scale(self, scale: float):
        """Scale the step by a scale factor

        Args:
            scale (float): Scale factor
        """
        self.volume *= scale
