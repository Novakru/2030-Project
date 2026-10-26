"""
.. module:: steps_utility.purge
    :platforms: Unix, Windows
    :synopsis: XDL steps related to purging the system with gases

"""

from typing import List, Optional
from networkx import MultiDiGraph

# XDL
from xdl.steps.base_steps import Step, AbstractStep
from xdl.steps.templates import (
    AbstractPurgeStep,
    AbstractStartPurgeStep,
    AbstractStopPurgeStep,
)
from xdl.constants import INERT_GAS_SYNONYMS, VESSEL_PROP_TYPE
from xdl.utils.misc import SanityCheck
from xdl.utils.prop_limits import TIME_PROP_LIMIT, PRESSURE_PROP_LIMIT

# Relative
from .general import Wait
from ..steps_utility import SwitchArgon, CleanBackboneDeprecated
from ..steps_base import CConnect, CValveMoveToPosition
from ..base_step import ChemputerStep
from ...utils.execution import (
    get_vacuum_configuration, node_in_graph
)
from ...utils.prop_limits import VALVE_PORT_PROP_LIMIT

class StartPurge(ChemputerStep, AbstractStartPurgeStep):

    INTERNAL_PROPS = [
        'pneumatic_controller',
        'inert_gas',
    ]

    PROP_TYPES = {
        'vessel': VESSEL_PROP_TYPE,
        'gas': str,
        'pressure': float,
        'flow_rate': float,
        'pneumatic_controller': str,
        'inert_gas': str,
    }

    DEFAULT_PROPS = {
        'pressure': None,
        'flow_rate': None,
        'gas': None,
    }

    PROP_LIMITS = {
        'pressure': PRESSURE_PROP_LIMIT,
    }

    def __init__(
        self,
        vessel: str,
        gas: Optional[str] = None,
        pressure: Optional[float] = 'default',
        flow_rate: Optional[float] = 'default',

        # Internal properties
        pneumatic_controller: str = None,
        inert_gas: str = None,
        **kwargs,
    ):
        super().__init__(locals())

    def on_prepare_for_execution(self, graph: MultiDiGraph):
        """Prepares the current step for execution.
        Gets/sets/cleans up appropriate items in preparation for exection.

        Args:
            graph (MultiDiGraph): Chemputer Graph to check
        """
        vacuum_info = get_vacuum_configuration(graph, self.vessel)
        if not self.inert_gas:
            self.inert_gas = vacuum_info['valve_inert_gas']

        self.pneumatic_controller = vacuum_info['pneumatic_controller']

    def sanity_checks(self, graph: MultiDiGraph) -> List[SanityCheck]:
        """Gets a list of Sanity checks to perform for the step

        Args:
            graph (MultiDiGraph): Chemputer graph to check

        Returns:
            List[SanityCheck]: List of checks to perform
        """

        return [
            SanityCheck(
                condition=self.pneumatic_controller or self.inert_gas,
                error_msg=f'Cannot find pneumatic controller or inert gas'
                          f' connected to {self.vessel} so cannot purge.'
            )
        ]

    def get_steps(self) -> Optional[List[Step]]:
        """Get the list of steps/base steps to execute.

        Returns:
            Optional[List[Step]]: Steps to execute. None if no method to purge
        """

        # Pneumatic controller is used, use argon line
        if self.pneumatic_controller:
            return [
                SwitchArgon(
                    vessel=self.vessel,
                    pressure='high',
                    after_switch_wait=None,
                ),
            ]

        # Using inert gas valve, switch valve to position
        elif self.inert_gas:
            return [
                CConnect(
                    from_vessel=self.inert_gas,
                    to_vessel=self.vessel,
                ),
            ]

        # No way to purge, return nothing
        else:
            return []

class StopPurge(ChemputerStep, AbstractStopPurgeStep):

    INTERNAL_PROPS = [
        'pneumatic_controller',
        'inert_gas',
        'inert_gas_valve',
        'inert_gas_valve_unused_port',
    ]

    PROP_TYPES = {
        'vessel': VESSEL_PROP_TYPE,
        'pneumatic_controller': str,
        'inert_gas': str,
        'inert_gas_valve': str,
        'inert_gas_valve_unused_port': int
    }

    PROP_LIMITS = {
        'inert_gas_valve_unused_port': VALVE_PORT_PROP_LIMIT,
    }

    def __init__(
        self,
        vessel: str,

        # Internal properties
        pneumatic_controller: str = None,
        inert_gas: str = None,
        inert_gas_valve: str = None,
        inert_gas_valve_unused_port: str = None,
        **kwargs
    ):
        super().__init__(locals())

    def sanity_checks(self, graph: MultiDiGraph):
        """Gets a list of Sanity checks to perform for the step

        Args:
            graph (MultiDiGraph): Chemputer graph to check

        Returns:
            List[SanityCheck]: List of checks to perform
        """

        return [
            SanityCheck(
                condition=self.pneumatic_controller or self.inert_gas,
                error_msg=f'Cannot find pneumatic controller or inert gas connected to\
 {self.vessel} so cannot purge.'
            ),

            SanityCheck(
                condition=node_in_graph(graph, self.vessel),
                error_msg=f'Unable to find {self.vessel} in graph.'
            )
        ]

    def on_prepare_for_execution(self, graph: MultiDiGraph):
        """Prepares the current step for execution.
        Gets/sets/cleans up appropriate items in preparation for exection.

        Args:
            graph (MultiDiGraph): Chemputer Graph to check
        """
        # Get vacuum information form the graph instead
        vacuum_info = get_vacuum_configuration(graph, self.vessel)
        self.pneumatic_controller = vacuum_info['pneumatic_controller']
        self.inert_gas = vacuum_info['valve_inert_gas']
        self.inert_gas_valve = vacuum_info['valve']
        self.inert_gas_valve_unused_port = vacuum_info[
            'valve_unused_port'
        ]

    def get_steps(self) -> Optional[List[Step]]:
        """Get the list of steps/base steps to execute.

        Returns:
            Optional[List[Step]]: Steps to execute.
        """

        # Using pneumatic controller, switch to Argon
        if self.pneumatic_controller:
            if self.inert_gas_valve:
                return [
                    SwitchArgon(
                        vessel=self.vessel,
                        pressure='low',
                        after_switch_wait=None,
                    ),
                    CValveMoveToPosition(
                        valve_name=self.inert_gas_valve,
                        position=self.inert_gas_valve_unused_port
                    ),
                ]
            return [
                SwitchArgon(
                    vessel=self.vessel,
                    pressure='low',
                    after_switch_wait=None,
                )
            ]

        # Using inert gas valve
        elif self.inert_gas:
            return [
                CValveMoveToPosition(
                    valve_name=self.inert_gas_valve,
                    position=self.inert_gas_valve_unused_port
                )
            ]

        # No method to purge, return nothing
        else:
            return []

class Purge(ChemputerStep, AbstractPurgeStep):

    DEFAULT_PROPS = {
        'time': '5 minutes',
        'gas': None,
        'pressure': None,
        'flow_rate': None,
    }

    PROP_TYPES = {
        'vessel': VESSEL_PROP_TYPE,
        'time': float,
        'gas': str,
        'pressure': float,
        'flow_rate': float,
    }

    PROP_LIMITS = {
        'time': TIME_PROP_LIMIT,
        'pressure': PRESSURE_PROP_LIMIT
    }

    def __init__(
        self,
        vessel: str,
        gas: Optional[str] = 'default',
        pressure: Optional[float] = 'default',
        flow_rate: Optional[float] = 'default',
        time: float = 'default',
        **kwargs,
    ):
        super().__init__(locals())

    def sanity_checks(self, graph: MultiDiGraph) -> List[SanityCheck]:
        """Gets a list of Sanity checks to perform for the step

        Args:
            graph (MultiDiGraph): Chemputer graph to check

        Returns:
            List[SanityCheck]: List of checks to perform
        """

        return [
            SanityCheck(
                condition=node_in_graph(graph, self.vessel),
                error_msg=f'Unable to find {self.vessel} in graph.',
            ),
            SanityCheck(
                condition=self.time > 0,
                error_msg='Purge time must be > 0.'
            ),
            SanityCheck(
                condition=self.pressure is None,
                error_msg='Pressure value can only be assigned None.'
            )
        ]

    def on_prepare_for_execution(self, graph: MultiDiGraph):
        """Prepares the current step for execution.
        Gets/sets/cleans up appropriate items in preparation for exection.

        Args:
            graph (MultiDiGraph): Chemputer Graph to check
        """

        return

    def get_steps(self) -> List[Step]:
        """Get the list of steps/base steps to execute.

        Returns:
            List[Step]: Steps to execute.
        """

        return [
            StartPurge(vessel=self.vessel),
            Wait(time=self.time),
            StopPurge(vessel=self.vessel)
        ]

class PurgeBackbone(ChemputerStep, AbstractStep):

    PROP_TYPES = {
        'purge_gas': str
    }

    DEFAULT_PROPS = {
        'purge_gas': None,
    }

    def __init__(
        self,
        purge_gas: str = 'default',
        **kwargs
    ):
        super().__init__(locals())

    def on_prepare_for_execution(self, graph: MultiDiGraph):
        """Prepares the current step for execution.
        Gets/sets/cleans up appropriate items in preparation for exection.

        Args:
            graph (MultiDiGraph): Chemputer Graph to check
        """

        # Purge gas is defined
        if self.purge_gas is None:
            # Iterate through all nodes in the graph
            for _, data in graph.nodes(data=True):
                # Current node is an inert gas flask, set the purge gas to that
                if (data['class'] == 'ChemputerFlask'
                        and data['chemical'] in INERT_GAS_SYNONYMS):
                    self.purge_gas = data['chemical']
                    break

    def sanity_checks(self, graph: MultiDiGraph) -> List[SanityCheck]:
        """Gets a list of Sanity checks to perform for the step

        Args:
            graph (MultiDiGraph): Chemputer graph to check

        Returns:
            List[SanityCheck]: List of checks to perform
        """

        return [
            SanityCheck(
                condition=self.purge_gas,
            ),
        ]

    def get_steps(self) -> List[Step]:
        """Get the list of steps/base steps to execute.

        Returns:
            List[Step]: Steps to execute.
        """

        return [
            CleanBackboneDeprecated(
                solvent=self.purge_gas,
            )
        ]
