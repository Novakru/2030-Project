"""
.. module:: steps_utility.pneumatic_controller
    :platforms: Unix, Windows
    :synopsis: XDL steps to interface with Pneumatic controller panel to
                control vacuum and inert gas.

"""

from typing import List
from networkx import MultiDiGraph

# XDL
from xdl.steps.base_steps import Step
from xdl.steps.base_steps import AbstractStep
from xdl.utils.misc import SanityCheck
from xdl.utils.prop_limits import TIME_PROP_LIMIT
from xdl.constants import VESSEL_PROP_TYPE

# Relative
from .general import Wait
from ..base_step import ChemputerStep
from ..steps_base import CSwitchVacuum, CSwitchArgon, CConnect
from ...utils.execution import get_vacuum_configuration
from ...utils.prop_limits import (
    PORT_PROP_LIMIT,
    PNEUMATIC_CONTROLLER_PORT_PROP_LIMIT,
    PNEUMATIC_CONTROLLER_PRESSURE_PROP_LIMIT,
)
from ...constants import PORT_PROP_TYPE

#: Time to wait after switching between argon/vacuum for pressure to change.
WAIT_AFTER_SWITCH_TIME = 30  # s

class PneumaticControllerMixin:
    """Mixin to supply methods used by both ``SwitchArgon`` and
    ``SwitchVacuum``.
    """
    def on_prepare_for_execution(self, graph: MultiDiGraph) -> None:
        """Get pneumatic controller, pneumatic controller port and determine if
        valve is being used to connect pneumatic controller to vessel.

        Args:
            graph (MultiDiGraph): Chemputer Graph to check
        """
        # Get the vacuum information
        vacuum_info = get_vacuum_configuration(graph, self.vessel, self.port)
        self.pneumatic_controller = vacuum_info['pneumatic_controller']
        self.pneumatic_controller_port =\
            vacuum_info['pneumatic_controller_port']
        self.vacuum_valve = vacuum_info['valve']

    def get_pneumatic_controller_connect_steps(self) -> List[Step]:
        """Connect pneumatic controller to vessel if it is connected through a
        valve or do nothing if it is connected directly.
        """
        if self.vacuum_valve:
            return [
                CConnect(
                    from_vessel=self.pneumatic_controller,
                    to_vessel=self.vessel,
                    to_port=self.port
                )
            ]
        return []

    def sanity_checks(self, graph: MultiDiGraph) -> List[SanityCheck]:
        return [
            SanityCheck(
                condition=self.pneumatic_controller is not None,
                error_msg='No pneumatic manifold found connected to'
                          f' {self.vessel} port {self.port}.'
            )
        ]


class SwitchVacuum(PneumaticControllerMixin, ChemputerStep, AbstractStep):
    """Supply given vessel with vacuum using PneumaticController.

    Args:
        vessel (str): Vessel to supply with vacuum.
        port (str): Port of vessel to supply with vacuum.
        pneumatic_controller (str): Internal property. Node name of pneumatic
            controller.
        pneumatic_controller_port (str): Internal property. Port of pneumatic
            controller attached to correct port of vessel.
    """

    DEFAULT_PROPS = {
        'after_switch_wait': '30 seconds',
        'port': None,
    }

    INTERNAL_PROPS = [
        'pneumatic_controller',
        'pneumatic_controller_port',
        'vacuum_valve',
    ]

    PROP_TYPES = {
        'vessel': VESSEL_PROP_TYPE,
        'port': PORT_PROP_TYPE,
        'after_switch_wait': float,
        'pneumatic_controller': str,
        'pneumatic_controller_port': int,
        'vacuum_valve': str,
    }

    PROP_LIMITS = {
        'port': PORT_PROP_LIMIT,
        'after_switch_wait': TIME_PROP_LIMIT,
        'pneumatic_controller_port': PNEUMATIC_CONTROLLER_PORT_PROP_LIMIT,
    }

    def __init__(
        self,
        vessel: str,
        port: str = 'default',
        after_switch_wait: float = 'default',

        # Internal properties
        vacuum_valve: str = None,
        pneumatic_controller: str = None,
        pneumatic_controller_port: str = None,
        **kwargs,
    ) -> None:
        super().__init__(locals())

    def get_steps(self) -> List[Step]:
        """Get the list of steps/base steps to execute.

        Returns:
            List[Step]: Steps to execute.
        """

        steps = self.get_pneumatic_controller_connect_steps() + [
            CSwitchVacuum(
                pneumatic_controller=self.pneumatic_controller,
                port=self.pneumatic_controller_port
            ),
        ]

        # Add Wait step if the wait flag is set
        if self.after_switch_wait:
            steps.append(
                Wait(time=self.after_switch_wait)
            )

        return steps

    def get_pneumatic_controller_connect_steps(self) -> List[Step]:
        if self.vacuum_valve:
            return [
                CConnect(
                    from_vessel=self.pneumatic_controller,
                    to_vessel=self.vessel,
                    to_port=self.port
                )
            ]
        return []

class SwitchArgon(PneumaticControllerMixin, ChemputerStep, AbstractStep):
    """Supply given vessel with argon using PneumaticController.

    Args:
        vessel (str): Vessel to supply with argon.
        port (str): Port of vessel to supply with argon.
        pressure (str): Argon pressure. 'high' or 'low'. Defaults to 'low'.
        pneumatic_controller (str): Internal property. Node name of pneumatic
            controller.
        pneumatic_controller_port (str): Internal property. Port of pneumatic
            controller attached to correct port of vessel.
    """

    DEFAULT_PROPS = {
        'after_switch_wait': '30 seconds',
        'port': None,
        'pressure': 'low',
    }

    INTERNAL_PROPS = [
        'pneumatic_controller',
        'pneumatic_controller_port',
        'vacuum_valve',
    ]

    PROP_TYPES = {
        'vessel': VESSEL_PROP_TYPE,
        'port': PORT_PROP_TYPE,
        'pressure': str,
        'after_switch_wait': float,
        'vacuum_valve': str,
        'pneumatic_controller': str,
        'pneumatic_controller_port': int,
    }

    PROP_LIMITS = {
        'port': PORT_PROP_LIMIT,
        'after_switch_wait': TIME_PROP_LIMIT,
        'pneumatic_controller_port': PNEUMATIC_CONTROLLER_PORT_PROP_LIMIT,
        'pressure': PNEUMATIC_CONTROLLER_PRESSURE_PROP_LIMIT,
    }

    def __init__(
        self,
        vessel: str,
        port: str = 'default',
        pressure: str = 'default',
        after_switch_wait: float = 'default',

        # Internal properties
        vacuum_valve: str = None,
        pneumatic_controller: str = None,
        pneumatic_controller_port: str = None,
        **kwargs,
    ) -> None:
        super().__init__(locals())

    def get_steps(self) -> List[Step]:
        """Get the list of steps/base steps to execute.

        Returns:
            List[Step]: Steps to execute.
        """

        steps = self.get_pneumatic_controller_connect_steps() + [
            CSwitchArgon(
                pneumatic_controller=self.pneumatic_controller,
                port=self.pneumatic_controller_port,
                pressure=self.pressure
            )
        ]

        # Add Wait if wait flag is set
        if self.after_switch_wait:
            steps.append(
                Wait(time=self.after_switch_wait)
            )

        return steps
