"""
.. module:: steps_utility.filter_dead_volume
    :platforms: Unix, Windows
    :synopsis: XDL steps to deal with dead volumes using a filter.

"""

from typing import Optional, List, Dict, Any, Union
from networkx import MultiDiGraph

from ..utils import get_vacuum_valve_reconnect_steps
from xdl.steps.base_steps import AbstractStep, Step
from xdl.constants import VESSEL_PROP_TYPE, REAGENT_PROP_TYPE
from ..base_step import ChemputerStep
from ..steps_base import CMove
from ...constants import BOTTOM_PORT, CHEMPUTER_WASTE
from ...utils.execution import (
    get_nearest_node, get_reagent_vessel, get_vacuum_configuration
)
from ...utils.prop_limits import VALVE_PORT_PROP_LIMIT
from xdl.utils.prop_limits import VOLUME_PROP_LIMIT

class AddFilterDeadVolume(ChemputerStep, AbstractStep):
    """Fill bottom of filter vessel with solvent in anticipation of the filter
    top being used.

    Args:
        filter_vessel (str): Filter vessel to fill dead volume with solvent.
        solvent (str): Solvent to fill filter bottom with.
        volume (int): Volume of filter bottom.
        waste_vessel (str): Given internally. Vessel to put waste material.
        solvent_vessel (str): Given internally. Vessel to take solvent from.
        vacuum (str): Given internally. Name of vacuum flask.
        inert_gas (str): Given internally. Name of node supplying inert gas.
            Only used if inert gas filter dead volume method is being used.
        vacuum_valve (str): Given internally. Name of valve connecting filter
            bottom to vacuum.
        valve_unused_port (str): Given internally. Random unused position on
            valve.
    """

    INTERNAL_PROPS = [
        'waste_vessel',
        'solvent_vessel',
        'vacuum',
        'inert_gas',
        'vacuum_valve',
        'valve_unused_port',
    ]

    PROP_TYPES = {
        'filter_vessel': VESSEL_PROP_TYPE,
        'solvent': REAGENT_PROP_TYPE,
        'volume': float,
        'waste_vessel': str,
        'solvent_vessel': str,
        'vacuum': str,
        'inert_gas': str,
        'vacuum_valve': str,
        'valve_unused_port': int
    }

    PROP_LIMITS = {
        'volume': VOLUME_PROP_LIMIT,
        'valve_unused_port': VALVE_PORT_PROP_LIMIT,
    }

    DO_NOT_SCALE = True

    def __init__(
        self,
        filter_vessel: str,
        solvent: str,
        volume: float,

        # Internal properties
        waste_vessel: Optional[str] = None,
        solvent_vessel: Optional[str] = None,
        vacuum: Optional[str] = None,
        inert_gas: Optional[str] = None,
        vacuum_valve: Optional[str] = None,
        valve_unused_port: Optional[Union[str, int]] = None,
        **kwargs
    ) -> None:
        super().__init__(locals())

    def on_prepare_for_execution(self, graph: MultiDiGraph):
        """Prepares the current step for execution.
        Gets/sets/cleans up appropriate items in preparation for exection.

        Args:
            graph (MultiDiGraph): Chemputer Graph to check
        """

        # Obtain the waste vessel if not defined
        if not self.waste_vessel:
            self.waste_vessel = get_nearest_node(
                graph, self.filter_vessel, CHEMPUTER_WASTE
            )

        # Obtain the solvent vessel if not defined
        if not self.solvent_vessel:
            self.solvent_vessel = get_reagent_vessel(graph, self.solvent)

        # Get vacuum information
        vacuum_info = get_vacuum_configuration(graph, self.filter_vessel)

        # Obtain the vacuum if not defined from the vacuum info
        if not self.vacuum:
            self.vacuum = vacuum_info['source']

        # Obtain the inert gas if not defined from the vacuum info
        if not self.inert_gas:
            self.inert_gas = vacuum_info['valve_inert_gas']

        # Obtain the vacuum valve if not defined from the vacuum info
        if not self.vacuum_valve:
            self.vacuum_valve = vacuum_info['valve']

        # Obtain the unused valve port if not defined from the vacuum info
        if not self.valve_unused_port:
            self.valve_unused_port = vacuum_info['valve_unused_port']

    def get_steps(self) -> List[Step]:
        """Get the list of steps/base steps to execute.

        Returns:
            List[Step]: Steps to execute.
        """

        steps = [
            CMove(
                from_vessel=self.solvent_vessel,
                volume=self.volume,
                to_vessel=self.filter_vessel,
                to_port=BOTTOM_PORT
            )
        ]

        # Reconnect vacuum valve to inert gas or unconnected port after done
        steps.extend(
            get_vacuum_valve_reconnect_steps(
                inert_gas=None,
                vacuum_valve=self.vacuum_valve,
                valve_unused_port=self.valve_unused_port,
                vessel=self.filter_vessel
            )
        )

        return steps

    @property
    def requirements(self) -> Dict[str, Dict[str, Any]]:
        """Gets the requirements needed for this step.

        Returns:
            Dict[str, Dict[str, Any]]: Requirements for the step.
        """

        return {
            'filter_vessel': {
                'filter': True,
            }
        }

class RemoveFilterDeadVolume(ChemputerStep, AbstractStep):
    """Remove dead volume (volume below filter) from filter vessel.

    Args:
        filter_vessel (str): Filter vessel to remove dead volume from.
        dead_volume (float): Volume in mL to remove from bottom of filter
            vessel.
        waste_vessel (str): Given internally. Waste vessel to send solvent to.
        vacuum (str): Given internally. Name of vacuum flask.
        inert_gas (str): Given internally. Name of node supplying inert gas.
            Only used if inert gas filter dead volume method is being used.
        vacuum_valve (str): Given internally. Name of valve connecting filter
            bottom to vacuum.
        valve_unused_port (str): Given internally. Random unused position on
            valve.
    """

    INTERNAL_PROPS = [
        'waste_vessel',
        'vacuum',
        'vacuum_valve',
        'valve_unused_port'
    ]

    PROP_TYPES = {
        'filter_vessel': VESSEL_PROP_TYPE,
        'dead_volume': float,
        'waste_vessel': str,
        'vacuum': str,
        'vacuum_valve': str,
        'valve_unused_port': int
    }

    PROP_LIMITS = {
        'dead_volume': VOLUME_PROP_LIMIT,
        'valve_unused_port': VALVE_PORT_PROP_LIMIT,
    }

    DO_NOT_SCALE = True

    def __init__(
        self,
        filter_vessel: str,
        dead_volume: Optional[float] = 0,

        # Internal properties
        waste_vessel: Optional[str] = None,
        vacuum: Optional[str] = None,
        vacuum_valve: Optional[str] = None,
        valve_unused_port: Optional[Union[str, int]] = None,
        **kwargs
    ) -> None:
        super().__init__(locals())

    def on_prepare_for_execution(self, graph: MultiDiGraph):
        """Prepares the current step for execution.
        Gets/sets/cleans up appropriate items in preparation for exection.

        Args:
            graph (MultiDiGraph): Chemputer Graph to check
        """

        # Obtain the waste vessel from the graph
        self.waste_vessel = get_nearest_node(
            graph, self.filter_vessel, CHEMPUTER_WASTE
        )

        # Obtain the vacuum information
        vacuum_info = get_vacuum_configuration(graph, self.filter_vessel)

        # Obtain the vacuum if not defined from the vacuum info
        if not self.vacuum:
            self.vacuum = vacuum_info['source']

        # Obtain the vacuum valve if not defined from the vacuum info
        if not self.vacuum_valve:
            self.vacuum_valve = vacuum_info['valve']

        # Obtain the unused valve port if not defined from the vacuum info
        if not self.valve_unused_port:
            self.valve_unused_port = vacuum_info['valve_unused_port']

    def get_steps(self) -> List[Step]:
        """Get the list of steps/base steps to execute.

        Returns:
            List[Step]: Steps to execute.
        """

        steps = [
            CMove(
                from_vessel=self.filter_vessel,
                from_port=BOTTOM_PORT,
                to_vessel=self.waste_vessel,
                volume=self.dead_volume
            )
        ]

        # Reconnect vacuum valve to inert gas or unconnected port after done
        steps.extend(
            get_vacuum_valve_reconnect_steps(
                inert_gas=None,
                vacuum_valve=self.vacuum_valve,
                valve_unused_port=self.valve_unused_port,
                vessel=self.filter_vessel
            )
        )

        return steps

    @property
    def requirements(self) -> Dict[str, Dict[str, Any]]:
        """Gets the requirements needed for this step.

        Returns:
            Dict[str, Dict[str, Any]]: Requirements for the step.
        """

        return {
            'filter_vessel': {
                'filter': True,
            }
        }
