"""
.. module:: steps_utility.rotavap
    :platforms: Unix, Windows
    :synopsis: XDL steps to interact with Rotavaps

"""

from typing import List, Dict, Any
from networkx import MultiDiGraph

# XDL
from xdl.steps.base_steps import AbstractStep, Step
from xdl.constants import VESSEL_PROP_TYPE

# Relative
from .vacuum import VentVacuum
from ..base_step import ChemputerStep
from ..steps_base import (
    CRotavapLiftUp,
    CPressureControllerStop,
    CTemperatureControllerStop,
    CStirringControllerStop,
)
from ...utils.execution import get_pressure_controller

class RotavapStopEverything(ChemputerStep, AbstractStep):
    """Stop vacuum, lift rotavap flask up, vent vacuum, stop heater and stop
    rotation.

    Args:
        rotavap_name (str): Name of rotavap to stop evaporating with.
    """

    PROP_TYPES = {
        'rotavap_name': VESSEL_PROP_TYPE,
        'pressure_controller': str,
    }

    INTERNAL_PROPS = ['pressure_controller']

    def __init__(
        self,
        rotavap_name: str,
        pressure_controller: str = None,
        **kwargs
    ) -> None:
        super().__init__(locals())

    def on_prepare_for_execution(self, graph: MultiDiGraph):
        if not self.pressure_controller:
            self.pressure_controller = get_pressure_controller(
                graph, self.rotavap_name)

    def get_steps(self) -> List[Step]:
        """Get the list of steps/base steps to execute.

        Returns:
            List[Step]: Steps to execute.
        """

        return [
            CPressureControllerStop(self.pressure_controller),
            CRotavapLiftUp(self.rotavap_name),
            VentVacuum(self.pressure_controller),
            CTemperatureControllerStop(self.rotavap_name),
            CStirringControllerStop(self.rotavap_name),
        ]

    @property
    def requirements(self) -> Dict[str, Dict[str, Any]]:
        """Get the requirements needed for this step

        Returns:
            Dict[str, Dict[str, Any]]: Step requirements
        """

        return {
            'rotavap_name': {
                'rotavap': True,
            }
        }
