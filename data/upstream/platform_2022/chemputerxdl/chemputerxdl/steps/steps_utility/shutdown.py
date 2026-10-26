"""
.. module:: steps_utility.shutdown
    :platforms: Unix, Windows
    :synopsis: XDL step to shut down all hardware at the end of a procedure

"""

from typing import List
from networkx import MultiDiGraph
from itertools import chain
from xdl.steps import AbstractStep
from xdl.steps.base_steps import Step
from ..base_step import ChemputerStep
from ..steps_base import (
    CRotavapLiftUp,
    CTemperatureControllerStop,
    CPressureControllerStop,
    CStirringControllerStop,
)
from ..steps_utility import VentVacuum
from ...constants import (
    CHILLER_CLASSES,
    HEATER_CLASSES,
    ROTAVAP_CLASSES,
    VACUUM_CLASSES,
    STIRRER_CLASSES,
    R300_ROTOVAP,
)

class Shutdown(ChemputerStep, AbstractStep):
    """XDL step to enact a Shutdown on the platform.
    Will iterate through all devices which can switch off.

    Inherits:
        AbstractStep, ChemputerStep
    """

    INTERNAL_PROPS = [
        'vacuums',
        'heaters',
        'stirrers',
        'rotavaps',
        'chillers'
    ]

    PROP_TYPES = {
        'vacuums': List[str],
        'heaters': List[str],
        'stirrers': List[str],
        'rotavaps': List[str],
        'chillers': List[str]
    }

    def __init__(
        self,
        # Internal properties
        vacuums: List[str] = [],
        heaters: List[str] = [],
        stirrers: List[str] = [],
        rotavaps: List[str] = [],
        chillers: List[str] = [],
        **kwargs
    ) -> None:
        super().__init__(locals())

    def get_rotavap_steps(self) -> List[Step]:
        """Get steps to shutdown the rotavap

        Returns:
            List[Step]: Rotavap shutdown steps
        """

        stop_rots = [
            CStirringControllerStop(rot)
            for rot in self.rotavaps
        ]

        stop_heats = [
            CTemperatureControllerStop(rot)
            for rot in self.rotavaps
        ]

        lifts = [
            CRotavapLiftUp(rot)
            for rot in self.rotavaps
        ]

        return list(
            chain(stop_rots, stop_heats, lifts)
        )

    def get_stirrer_steps(self) -> List[Step]:
        """Get steps to shutdown the stirrers

        Returns:
            List[Step]: Stirrer shutdown steps
        """

        return [
            CStirringControllerStop(stir)
            for stir in self.stirrers
        ]

    def get_heater_steps(self) -> List[Step]:
        """Get steps to shutdown the heaters

        Returns:
            List[Step]: HEater shutdown steps
        """

        steps = []
        for hotplate in self.heaters:
            steps.extend([
                CStirringControllerStop(hotplate),
                CTemperatureControllerStop(hotplate)
            ])
        return steps

    def get_vacuum_steps(self) -> List[Step]:
        """Get the steps to shutdown the vacuums

        Returns:
            List[Step]: Vacuum shutdowen steps
        """

        steps = []
        for vac in self.vacuums:
            steps.extend([
                CPressureControllerStop(vac),
                VentVacuum(vac)
            ])

        return steps

    def get_chiller_steps(self) -> List[Step]:
        """Get the steps to shutdown the chillers

        Returns:
            List[Step]: Chiller shutdown steps
        """

        return [
            CTemperatureControllerStop(chill)
            for chill in self.chillers
        ]

    def on_prepare_for_execution(self, graph: MultiDiGraph):
        """Prepares the current step for execution.
        Gets/sets/cleans up appropriate items in preparation for exection.

        Args:
            graph (MultiDiGraph): Chemputer Graph to check
        """

        # Lists to hold hardware types
        chillers, stirrers, heaters, rotavaps, vacuums = [], [], [], [], []

        # Iterate through all nodes in the graph
        for node, data in graph.nodes(data=True):

            # Chiller vessel
            if data["class"] in CHILLER_CLASSES:
                chillers.append(node)

            # Heater vessel
            elif data["class"] in HEATER_CLASSES:
                heaters.append(node)

            # Stirrer vessel
            elif data["class"] in STIRRER_CLASSES:
                stirrers.append(node)

            # Rotavap vessel
            elif data["class"] in ROTAVAP_CLASSES:
                rotavaps.append(node)

            # Vacuum vessel
            elif data["class"] in VACUUM_CLASSES + [R300_ROTOVAP]:
                vacuums.append(node)

        # Set all hardware
        self.chillers = chillers
        self.rotavaps = rotavaps
        self.vacuums = vacuums
        self.heaters = heaters
        self.stirrers = stirrers

    def get_steps(self) -> List[Step]:
        """Get the list of steps/base steps to execute.

        Returns:
            List[Step]: Steps to execute.
        """

        return list(
            chain(
                self.get_rotavap_steps(),
                self.get_stirrer_steps(),
                self.get_heater_steps(),
                self.get_vacuum_steps(),
                self.get_chiller_steps(),
            )
        )
