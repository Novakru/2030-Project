"""
.. module:: steps_utility.evacuate
    :platforms: Unix, Windows
    :synopsis: XDL steps to deal with evacuating a vessel with an inert gas
                or vacuum

"""

from typing import Optional, List
from networkx import MultiDiGraph

from xdl.steps.base_steps import Step
from xdl.utils.misc import SanityCheck
from xdl.utils.prop_limits import TIME_PROP_LIMIT, PRESSURE_PROP_LIMIT
from xdl.steps.special_steps import Repeat
from xdl.constants import VESSEL_PROP_TYPE

from xdl.steps.templates import AbstractEvacuateAndRefillStep
from ..base_step import ChemputerStep
from ..steps_utility import (
    Wait, StartVacuum, StopVacuum, SwitchArgon, SwitchVacuum)
from ..steps_base import CConnect
from ...utils.execution import (
    get_vacuum_configuration, get_vessel_type)
from ...utils.prop_limits import VESSEL_TYPE_PROP_LIMIT

class EvacuateAndRefill(ChemputerStep, AbstractEvacuateAndRefillStep):
    """Evacuate given vessel with inert gas.

    Args:
        vessel (str): Vessel to evacuate with inert gas.
        repeats (int): Number of repeats to perform. Defaults to 3.
        after_inert_gas_wait_time (int): Time to wait for after connecting to
            inert gas. Defaults to 1 min.
        after_vacuum_wait_time (int): Time to wait for after connecting to
            vacuum. Defaults to 1 min.
        inert_gas (str): Internal property. Inert gas flask.
        vacuum (str): Internal property. Valve connected to vacuum.
    """

    #: Extra time in seconds to apply vacuum for on the first cycle of
    #: evacuation as the vacuum pump may take some time to reach the required
    #: pressure.
    FIRST_VACUUM_EXTRA_TIME: int = 60

    DEFAULT_PROPS = {
        'after_inert_gas_wait_time': '1 minute',
        'after_vacuum_wait_time': '1 minute',
        'repeats': 3,
        'vacuum_pressure': '50 mbar',
        'gas': None,
    }

    INTERNAL_PROPS = [
        'inert_gas',
        'vacuum',
        'vacuum_device',
        'vessel_type',
        'pneumatic_controller',
    ]

    PROP_TYPES = {
        'vessel': VESSEL_PROP_TYPE,
        'gas': str,
        'repeats': int,
        'after_inert_gas_wait_time': float,
        'after_vacuum_wait_time': float,
        'vacuum_pressure': float,
        'inert_gas': str,
        'vacuum': str,
        'vacuum_device': str,
        'vessel_type': str,
        'pneumatic_controller': str
    }

    PROP_LIMITS = {
        'after_inert_gas_wait_time': TIME_PROP_LIMIT,
        'after_vacuum_wait_time': TIME_PROP_LIMIT,
        'vacuum_pressure': PRESSURE_PROP_LIMIT,
        'vessel_type': VESSEL_TYPE_PROP_LIMIT,
    }

    def __init__(
        self,
        vessel: str,
        repeats: int = 'default',
        gas: Optional[str] = 'default',
        after_inert_gas_wait_time: Optional[float] = 'default',
        after_vacuum_wait_time: Optional[float] = 'default',
        vacuum_pressure: Optional[float] = 'default',

        # Internal properties
        inert_gas: Optional[str] = None,
        vacuum: Optional[str] = None,
        vacuum_device: Optional[str] = None,
        vessel_type: Optional[str] = None,
        pneumatic_controller: Optional[str] = None,
        **kwargs
    ) -> None:
        super().__init__(locals())

    def on_prepare_for_execution(self, graph: MultiDiGraph):
        """Prepares the current step for execution.
        Gets/sets/cleans up appropriate items in preparation for exection.

        Args:
            graph (MultiDiGraph): Chemputer Graph to check
        """
        self.vessel_type = get_vessel_type(graph, self.vessel)

        # Get the vacuum information
        vacuum_info = get_vacuum_configuration(graph, self.vessel)
        self.pneumatic_controller = vacuum_info['pneumatic_controller']
        self.vacuum = vacuum_info['source']
        self.vacuum_device = vacuum_info['device']
        self.inert_gas = vacuum_info['valve_inert_gas']

    def sanity_checks(self, graph: MultiDiGraph) -> List[SanityCheck]:
        """Gets a list of Sanity checks to perform for the step

        Args:
            graph (MultiDiGraph): Chemputer graph to check

        Returns:
            List[SanityCheck]: List of checks to perform
        """

        return [
            SanityCheck(
                self.pneumatic_controller or (self.vacuum and self.inert_gas),
                f'Cannot find pneumatic controller or vacuum and inert gas\
 connected to {self.vessel}. No way to perform evacuation.',
            ),
        ]

    def get_steps(self) -> Optional[List[Step]]:
        """Get the list of steps/base steps to execute.

        Returns:
            Optional[List[Step]]: Steps to execute. None if no vacuum or gas
        """

        # Get the Steps using the pneumatic controller
        if self.pneumatic_controller:
            return self.get_pneumatic_controller_steps()

        # Get the steps using thew vacuum and inert gas
        elif self.vacuum and self.inert_gas:
            return self.get_vacuum_inert_gas_valve_steps()

        # No steps
        else:
            return []

    def get_vacuum_inert_gas_valve_steps(self) -> List[Step]:
        """Get list of steps to evacuate a vessel with vacuum and inert gas

        Returns:
            List[Step]: Steps to execute
        """

        # Get the vacuum vessel
        vacuum_vessel = (
            self.vessel if self.vessel_type == 'rotavap' else self.vacuum
        )

        # Have a vacuum device
        if self.vacuum_device:
            steps = [
                # Start the vacuum
                StartVacuum(
                    vessel=vacuum_vessel, pressure=self.vacuum_pressure
                ),

                # Connect the vessel to the vacuum
                CConnect(self.vessel, self.vacuum),

                # Wait for evacuation
                Wait(
                    self.after_vacuum_wait_time + self.FIRST_VACUUM_EXTRA_TIME),

                # Connect vessel to inert gas line
                CConnect(self.inert_gas, self.vessel),

                # Wait for purge of inert gas
                Wait(self.after_inert_gas_wait_time),

                # Repeat for the evacuation and inert gas purge for the total
                # number of repeats required
                Repeat(
                    repeats=self.repeats - 1,
                    children=[
                        CConnect(self.vessel, self.vacuum),
                        Wait(self.after_vacuum_wait_time),
                        CConnect(self.inert_gas, self.vessel),
                        Wait(self.after_inert_gas_wait_time),
                    ]
                ),

                # Finally stop the vacuum
                StopVacuum(vessel=vacuum_vessel)
            ]

        # No vacuum device
        else:
            # Steps are a repeat of the connection to vacuum and inert gas
            steps = [
                Repeat(
                    repeats=self.repeats,
                    children=[
                        CConnect(self.vessel, self.vacuum),
                        Wait(self.after_vacuum_wait_time),
                        CConnect(self.inert_gas, self.vessel),
                        Wait(self.after_inert_gas_wait_time),
                    ]
                )
            ]

        return steps

    def get_pneumatic_controller_steps(self) -> List[Step]:
        """Get steps related to using the Pneumatic controller for
        repeats.

        Returns:
            List[Step]: Steps to execute
        """

        steps = [
            # Repeat steps of switching to vacuum and switching to Argon
            Repeat(
                repeats=self.repeats,
                children=[
                    SwitchVacuum(
                        vessel=self.vessel,
                        after_switch_wait=self.after_vacuum_wait_time
                    ),
                    SwitchArgon(
                        vessel=self.vessel,
                        pressure='high',
                        after_switch_wait=self.after_inert_gas_wait_time
                    )
                ]
            ),

            # End with finally switching to Argon
            SwitchArgon(
                vessel=self.vessel,
                pressure='low',
            ),
        ]

        return steps
