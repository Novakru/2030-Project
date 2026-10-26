"""
.. module:: steps_utility.vacuum
    :platforms: Unix, Windows
    :synopsis: XDL steps to interact with vacuum devices

"""

from typing import List, Optional
from networkx import MultiDiGraph

# XDL
from xdl.steps.base_steps import Step, AbstractStep, AbstractDynamicStep
from xdl.steps.utils import FTNDuration
from xdl.utils.misc import SanityCheck
from xdl.utils.graph import undirected_neighbors
from xdl.utils.prop_limits import PRESSURE_PROP_LIMIT, TIME_PROP_LIMIT
from xdl.constants import VESSEL_PROP_TYPE

#  Relative
from .pneumatic_controller import SwitchArgon, SwitchVacuum
from .general import Wait
from ..base_step import ChemputerStep
from ..steps_base import (
    CPressureControllerStart,
    CPressureControllerStop,
    CPressureControllerSetPressure,
    CPressureControllerVentOn,
    CPressureControllerVentOff,
    CPressureControllerGetPressure,
    CConnect,
    CValveMoveToPosition,
)
from ...utils.execution import (
    get_vacuum_configuration,
    get_vessel_type,
    get_pressure_controller,
)
from ...utils.prop_limits import (
    VESSEL_TYPE_PROP_LIMIT, VALVE_PORT_PROP_LIMIT, PORT_PROP_LIMIT
)
from ...constants import VACUUM_CLASSES, PORT_PROP_TYPE

class VentVacuum(ChemputerStep, AbstractDynamicStep):
    """Vent vacuum until pressure returns to atmospheric pressure."""

    ATMOSPHERIC_PRESSURE = 900
    finished = False

    PROP_TYPES = {
        'vessel': str,
        'pressure_controller': str,
    }

    INTERNAL_PROPS = ['pressure_controller']

    def __init__(
        self,
        vessel: str,
        pressure_controller: Optional[str] = None,
        **kwargs
    ):
        super().__init__(locals())

    def on_prepare_for_execution(self, graph: MultiDiGraph):
        if not self.pressure_controller:
            self.pressure_controller = get_pressure_controller(
                graph, self.vessel)

    def on_start(self):
        return [CPressureControllerVentOn(self.pressure_controller)]

    def on_continue(self):
        if self.finished:
            return []

        return [
            CPressureControllerGetPressure(
                self.pressure_controller, self.on_pressure_reading),
            Wait(5),
        ]

    def on_finish(self):
        return [CPressureControllerVentOff(self.pressure_controller)]

    def on_pressure_reading(self, reading):
        if reading > self.ATMOSPHERIC_PRESSURE:
            self.finished = True

    def duration(self, graph: MultiDiGraph) -> FTNDuration:
        # Educated guess. Not measured.
        return FTNDuration(5, 10, 30)

class StartVacuum(ChemputerStep, AbstractStep):
    """Start vacuum pump attached to given vessel.

    Args:
        vessel (str): Vessel name to start vacuum on.
        pressure (float): Pressure to set vacuum to.
        pressure_controller (str): Node name of pressure controller.
    """

    DEFAULT_PROPS = {
        'pressure': '400 mbar',
    }

    PROP_TYPES = {
        'vessel': VESSEL_PROP_TYPE,
        'pressure': float,
        'pressure_controller': str,
    }

    PROP_LIMITS = {
        'pressure': PRESSURE_PROP_LIMIT
    }

    INTERNAL_PROPS = ['pressure_controller']

    def __init__(
        self,
        vessel: str,
        pressure: float = 'default',

        # Internal properties
        pressure_controller: Optional[str] = None,
        **kwargs
    ) -> None:
        super().__init__(locals())

    def on_prepare_for_execution(self, graph: MultiDiGraph):
        self.pressure_controller = get_pressure_controller(graph, self.vessel)

    def get_steps(self) -> List[Step]:
        """Get the list of steps/base steps to execute.

        Returns:
            List[Step]: Steps to execute.
        """

        return [
            CPressureControllerSetPressure(
                pressure_controller=self.pressure_controller,
                pressure=self.pressure
            ),
            CPressureControllerStart(self.pressure_controller)
        ]

class StopVacuum(ChemputerStep, AbstractStep):
    """Stop vacuum pump attached to given vessel.

    Args:
        vessel (str): Vessel name to stop vacuum on.
    """

    PROP_TYPES = {
        'vessel': VESSEL_PROP_TYPE,
        'pressure_controller': str,
    }

    INTERNAL_PROPS = ['pressure_controller']

    def __init__(
        self,
        vessel: str,

        # Internal properties
        pressure_controller: Optional[str] = None,
        **kwargs
    ) -> None:
        super().__init__(locals())

    def on_prepare_for_execution(self, graph: MultiDiGraph):
        self.pressure_controller = get_pressure_controller(graph, self.vessel)

    def get_steps(self) -> List[Step]:
        """Get the list of steps/base steps to execute.

        Returns:
            List[Step]: Steps to execute.
        """
        return [CPressureControllerStop(self.pressure_controller)]

class ApplyVacuum(ChemputerStep, AbstractStep):
    """Apply vacuum to given vessel for given amount of time.
    Assumes one of following hardware setups:
        (Optional CVC3000) -> ChemputerVacuum <- ChemputerValve <-> vessel
        OR
        pneumatic_controller <-> vessel
        OR
        rotavap
    """

    DEFAULT_PROPS = {
        'pressure': '400 mbar',
        'port': None,
    }

    INTERNAL_PROPS = [
        'vessel_type',
        'vacuum_valve',
        'vacuum_source',
        'vacuum_device',
        'vacuum_valve_inert_gas',
        'vacuum_valve_unused_port',
        'pneumatic_controller'
    ]

    PROP_TYPES = {
        'vessel': VESSEL_PROP_TYPE,
        'time': float,
        'pressure': float,
        'port': PORT_PROP_TYPE,
        'vessel_type': str,
        'vacuum_valve': str,
        'vacuum_source': str,
        'vacuum_device': str,
        'vacuum_valve_inert_gas': str,
        'vacuum_valve_unused_port': int,
        'pneumatic_controller': str
    }

    PROP_LIMITS = {
        'pressure': PRESSURE_PROP_LIMIT,
        'time': TIME_PROP_LIMIT,
        'port': PORT_PROP_LIMIT,
        'vessel_type': VESSEL_TYPE_PROP_LIMIT,
        'vacuum_valve_unused_port': VALVE_PORT_PROP_LIMIT,
    }

    def __init__(
        self,
        vessel: str,
        time: float,
        pressure: float = 'default',
        port: str = 'default',

        # Internal properties
        vessel_type: str = None,
        vacuum_valve: str = None,
        vacuum_source: str = None,
        vacuum_device: str = None,
        vacuum_valve_inert_gas: str = None,
        vacuum_valve_unused_port: str = None,
        pneumatic_controller: str = None,
        **kwargs
    ) -> None:
        super().__init__(locals())

    def on_prepare_for_execution(self, graph: MultiDiGraph):
        """Prepares the current step for execution.
        Gets/sets/cleans up appropriate items in preparation for exection.

        Args:
            graph (MultiDiGraph): Chemputer Graph to check
        """

        # Obtian the vessel type
        self.vessel_type = get_vessel_type(graph, self.vessel)

        # Rotavap
        if self.vessel_type == 'rotavap':
            # Iterate through all neighbors of rotavap
            for neighbor, data in undirected_neighbors(
                    graph, self.vessel, data=True):

                # Found a vacuum attached
                if data['class'] in VACUUM_CLASSES:
                    self.vacuum_device = neighbor
                    break

        # Not a rotavap
        else:
            # Get vacuum information
            vacuum_info = get_vacuum_configuration(graph, self.vessel)

            # Extract all vacuum related info
            self.pneumatic_controller = vacuum_info['pneumatic_controller']
            self.vacuum_valve = vacuum_info['valve']
            self.vacuum_source = vacuum_info['source']
            self.vacuum_device = vacuum_info['device']
            self.vacuum_valve_inert_gas_ = vacuum_info['valve_inert_gas']
            self.vacuum_valve_unused_port = vacuum_info['valve_unused_port']

    def sanity_checks(self, graph: MultiDiGraph) -> List[SanityCheck]:
        """Gets a list of Sanity checks to perform for the step

        Args:
            graph (MultiDiGraph): Chemputer graph to check

        Returns:
            List[SanityCheck]: List of checks to perform
        """

        return [
            SanityCheck(
                condition=self.vessel in graph.nodes(),
                error_msg=f'vessel {self.vessel} not found in graph.',
            ),

            SanityCheck(
                condition=(
                    self.pneumatic_controller
                    or (self.vacuum_valve and self.vacuum_source)
                    or (self.vessel_type == 'rotavap')
                ),
                error_msg='Neither of valid hardware setups found.\n\
 Option 1: vessel <-> pneumatic controller\n\
 Option 2: vessel <-> valve -> vacuum <- (Optional vacuum device)',
            ),

            SanityCheck(
                condition=(
                    self.pneumatic_controller
                    or self.vessel_type == 'rotavap'
                    or (self.vacuum_valve_inert_gas is not None
                        or self.vacuum_valve_unused_port is not None)
                ),
                error_msg='Using vacuum valve, but cannot find inert gas or an unused\
 port to connect to after applying vacuum.',
            ),

            SanityCheck(
                condition=self.time > 0,
                error_msg='time property must be > 0',
            ),

            SanityCheck(
                condition=self.vessel_type != 'rotavap' or self.vacuum_device,
                error_msg='Drying in rotavap, but no vacuum pump found.'
            )
        ]

    def get_steps(self) -> List[Step]:
        """Get the list of steps/base steps to execute.

        Returns:
            List[Step]: Steps to execute.
        """

        # Get pneumatic controlelr steps
        if self.pneumatic_controller:
            return self.get_pneumatic_controller_steps()

        # Get rotavap steps
        elif self.vessel_type == 'rotavap':
            return self.get_rotavap_steps()

        # Get default steps
        else:
            return self.get_vacuum_valve_steps()

    def get_rotavap_steps(self) -> List[Step]:
        """Gets a list of steps for using a Rotavap

        Returns:
            List[Step]: Rotavap steps
        """

        return (
            self.get_start_vacuum_step()
            + self.get_wait_step()
            + self.get_stop_vacuum_step()
            + self.get_vent_vacuum_step()
        )

    def get_pneumatic_controller_steps(self) -> List[Step]:
        """Gets a list of steps for using a Pneumatic control panel

        Returns:
            List[Step]: Pneumatic controller steps
        """

        return [
            SwitchVacuum(self.vessel),
            Wait(self.time),
            SwitchArgon(self.vessel, pressure='low'),
        ]

    def get_vacuum_valve_steps(self) -> List[Step]:
        """Gets a list of steps using a vacuum line attached through a valve

        Returns:
            List[Step]: Vacuum valve steps
        """

        return (
            self.get_start_vacuum_step()
            + self.get_connect_vacuum_step()
            + self.get_wait_step()
            + self.get_vacuum_valve_reconnect_step()
            + self.get_stop_vacuum_step()
            + self.get_vent_vacuum_step()
        )

    def get_start_vacuum_step(self) -> Optional[List[Step]]:
        """Gets steps to start the vacuum depending on vessel type

        Returns:
            Optional[List[Step]]: Vacuum start steps, None if no vacuum.
        """

        # Using a rotavap
        if self.vessel_type == 'rotavap' and self.vacuum_device:
            return [
                StartVacuum(
                    vessel=self.vessel,
                    pressure=self.pressure
                )
            ]

        # Using a vacuum only
        elif self.vacuum_device:
            return [
                StartVacuum(
                    vessel=self.vacuum_source,
                    pressure=self.pressure
                )
            ]

        # No vacuum
        return []

    def get_connect_vacuum_step(self) -> List[Step]:
        """Connects the vessel to the vacuum source

        Returns:
            List[Step]: Connect step
        """

        return [
            CConnect(
                from_vessel=self.vessel,
                to_vessel=self.vacuum_source,
                from_port=self.port
            )
        ]

    def get_wait_step(self) -> List[Step]:
        """Gets a Wait step

        Returns:
            List[Step]: Wait step
        """

        return [
            Wait(self.time),
        ]

    def get_vacuum_valve_reconnect_step(self) -> Optional[List[Step]]:
        """Steps to reconnect to the vacuum source

        Returns:
            Optional[List[Step]]: Connection steps, None if not required
        """

        # Using inert gas through a valve
        if self.vacuum_valve_inert_gas:
            return [
                CConnect(
                    from_vessel=self.vacuum_valve_inert_gas,
                    to_vessel=self.vessel
                )
            ]

        # Using the vacuum port, switch to it
        elif self.vacuum_valve_unused_port is not None:
            return [
                CValveMoveToPosition(
                    valve_name=self.vacuum_valve,
                    position=self.vacuum_valve_unused_port
                )
            ]

        # Not required
        return []

    def get_stop_vacuum_step(self) -> Optional[List[Step]]:
        """Stops the vacuum

        Returns:
            Optional[List[Step]]: Stop vacuums teps, none if not required
        """

        # Using a rotavap
        if self.vessel_type == 'rotavap' and self.vacuum_device:
            return [
                StopVacuum(vessel=self.vessel)
            ]

        # Using a vacuum only
        elif self.vacuum_device:
            return [
                StopVacuum(vessel=self.vacuum_source)
            ]

        # Not required
        return []

    def get_vent_vacuum_step(self) -> Optional[List[Step]]:
        """Vents the vacuum

        Returns:
            Optional[List[Step]]: Vent vacuum steps, None if not required
        """

        # Using a rotavap
        if self.vessel_type == 'rotavap':
            return [
                VentVacuum(vessel=self.vessel)
            ]

        # Using a vacuum device only
        elif self.vacuum_device:
            return [
                VentVacuum(vessel=self.vacuum_source)
            ]

        # Not required
        return []
