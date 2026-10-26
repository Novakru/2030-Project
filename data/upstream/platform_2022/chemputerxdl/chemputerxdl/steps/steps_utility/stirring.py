"""
.. module:: steps_utility.stirring
    :platforms: Unix, Windows
    :synopsis: XDL steps to interact with stirring hardware

"""

from typing import Optional, Dict, Any, List
from networkx import MultiDiGraph

# XDL
from xdl.steps.base_steps import AbstractStep, Step
from xdl.steps.templates import (
    AbstractStirStep,
    AbstractStopStirStep,
    AbstractStartStirStep
)
from xdl.constants import VESSEL_PROP_TYPE

# Relative
from .general import Wait
from ..base_step import ChemputerStep
from ..steps_base import (
    CStirringControllerStart,
    CStirringControllerStop,
    CStirringControllerSetSpeed,
)
from ...utils.execution import get_stirring_controller
from xdl.utils.prop_limits import (
    ROTATION_SPEED_PROP_LIMIT,
    TIME_PROP_LIMIT,
    STIR_PURPOSE_PROP_LIMIT
)

class SetStirRate(ChemputerStep, AbstractStep):
    """Set stir rate. Works on rotavap, reactor or filter.

    Args:
        vessel (str): Vessel to set stir rate for.
        stir_speed (float): Stir rate in RPM
        stirring_controller (str): Node name of stirring controller.
    """

    PROP_TYPES = {
        'vessel': VESSEL_PROP_TYPE,
        'stir_speed': float,
        'stirring_controller': str,
    }

    PROP_LIMITS = {
        'stir_speed': ROTATION_SPEED_PROP_LIMIT,
    }

    INTERNAL_PROPS = ['stirring_controller']

    def __init__(
        self,
        vessel: str,
        stir_speed: float,

        # Internal properties
        stirring_controller: Optional[str] = None,
        **kwargs
    ) -> None:
        super().__init__(locals())

    def on_prepare_for_execution(self, graph: MultiDiGraph):
        """Prepares the current step for execution.
        Gets/sets/cleans up appropriate items in preparation for exection.

        Args:
            graph (MultiDiGraph): Chemputer Graph to check
        """
        self.stirring_controller = get_stirring_controller(graph, self.vessel)

    def get_steps(self) -> List[Step]:
        """Get the list of steps/base steps to execute.

        Returns:
            List[Step]: Steps to execute.
        """
        return [
            CStirringControllerSetSpeed(
                self.stirring_controller, self.stir_speed)
        ]

class StartStir(ChemputerStep, AbstractStartStirStep):
    """Start stirring given vessel.

    Args:
        vessel (str): Vessel name to stir.
        purpose (str): Purpose of stirring. Either None or 'dissolve'.
        stir_speed (int, optional): Speed in RPM to stir at.
        stirring_controller (str): Stirring controller associated with vessel.
    """

    DEFAULT_PROPS = {
        'purpose': None,
        'stir_speed': '250 RPM',
    }

    INTERNAL_PROPS = [
        'stirring_controller'
    ]

    PROP_TYPES = {
        'vessel': VESSEL_PROP_TYPE,
        'stir_speed': float,
        'purpose': str,
        'stirring_controller': str,
    }

    PROP_LIMITS = {
        'stir_speed': ROTATION_SPEED_PROP_LIMIT,
        'purpose': STIR_PURPOSE_PROP_LIMIT,
    }

    def __init__(
        self,
        vessel: str,
        stir_speed: Optional[float] = 'default',
        purpose: Optional[str] = 'default',

        # Internal properties
        stirring_controller: Optional[str] = None,
        **kwargs
    ) -> None:
        super().__init__(locals())

    def on_prepare_for_execution(self, graph: MultiDiGraph):
        """Prepares the current step for execution.
        Gets/sets/cleans up appropriate items in preparation for exection.

        Args:
            graph (MultiDiGraph): Chemputer Graph to check
        """
        self.stirring_controller = get_stirring_controller(graph, self.vessel)

    def get_steps(self) -> List[Step]:
        """Get the list of steps/base steps to execute.

        Returns:
            List[Step]: Steps to execute.
        """
        return [
            CStirringControllerSetSpeed(
                self.stirring_controller,
                self.stir_speed
            ),
            CStirringControllerStart(self.stirring_controller),
        ]

    @property
    def requirements(self) -> Dict[str, Dict[str, Any]]:
        """Get the requirements needed for this step

        Returns:
            Dict[str, Dict[str, Any]]: Step requirements
        """

        return {
            'vessel': {
                'stir': True
            }
        }

class StopStir(ChemputerStep, AbstractStopStirStep):
    """Stop stirring given vessel.

    Args:
        vessel (str): Vessel name to stop stirring.
        stirring_controller (str): Node name of stirring controller.
    """

    PROP_TYPES = {
        'vessel': VESSEL_PROP_TYPE,
        'stirring_controller': str,
    }

    INTERNAL_PROPS = ['stirring_controller']

    def __init__(
        self,
        vessel: str,

        # Internal properties
        stirring_controller: Optional[str] = None,
        **kwargs
    ) -> None:
        super().__init__(locals())

    def on_prepare_for_execution(self, graph: MultiDiGraph):
        """Prepares the current step for execution.
        Gets/sets/cleans up appropriate items in preparation for exection.

        Args:
            graph (MultiDiGraph): Chemputer Graph to check
        """
        self.stirring_controller = get_stirring_controller(graph, self.vessel)

    def get_steps(self) -> Optional[List[Step]]:
        """Get the list of steps/base steps to execute.

        Returns:
            Optional[List[Step]]: Steps to execute. None if no stirrer
        """

        # Stop stirring if stirrer is present
        if self.stirring_controller:
            return [CStirringControllerStop(self.stirring_controller)]

        # No stirrer present
        return []

class Stir(ChemputerStep, AbstractStirStep):
    """Stir given vessel for given time at room temperature.

    Args:
        vessel (str): Vessel to stir.
        time (float): Time to stir for.
        continue_stirring (bool): Continue stirring after stirring time elapses.
        stir_speed (float): Stir rate in RPM.
        purpose (str): Purpose of stirring. Either None or 'dissolve'.
    """

    DEFAULT_PROPS = {
        'stir_speed': '250 RPM',
        'continue_stirring': False,
        'purpose': None,
    }

    PROP_TYPES = {
        'vessel': VESSEL_PROP_TYPE,
        'time': float,
        'continue_stirring': bool,
        'stir_speed': float,
        'purpose': str,
    }

    PROP_LIMITS = {
        'stir_speed': ROTATION_SPEED_PROP_LIMIT,
        'purpose': STIR_PURPOSE_PROP_LIMIT,
        'time': TIME_PROP_LIMIT,
    }

    def __init__(
        self,
        vessel: str,
        time: float,
        continue_stirring: bool = 'default',
        stir_speed: Optional[float] = 'default',
        purpose: Optional[str] = 'default',
        **kwargs
    ) -> None:
        super().__init__(locals())

    def get_steps(self) -> List[Step]:
        """Get the list of steps/base steps to execute.

        Returns:
            List[Step]: Steps to execute.
        """
        # Start stirring and wait for given time
        steps = [
            StartStir(vessel=self.vessel, stir_speed=self.stir_speed),
            Wait(time=self.time),
        ]

        # Stirring should continue, return
        if self.continue_stirring is True:
            return steps

        # Stirring should stop, add a StopStir
        else:
            steps.append(StopStir(vessel=self.vessel))
            return steps

    @property
    def requirements(self) -> Dict[str, Dict[str, Any]]:
        """Get the requirements needed for this step

        Returns:
            Dict[str, Dict[str, Any]]: Step requirements
        """

        return {
            'vessel': {
                'stir': True,
            }
        }
