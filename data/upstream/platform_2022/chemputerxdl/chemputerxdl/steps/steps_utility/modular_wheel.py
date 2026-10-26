"""
.. module:: steps_utility.modular_wheel
    :platforms: Unix, Windows
    :synopsis: XDL steps to interact with the Modular Wheel system

"""

from typing import Optional, List
from networkx import MultiDiGraph

# XDL
from xdl.utils.misc import SanityCheck
from xdl.steps.base_steps import Step
from xdl.steps.base_steps import AbstractStep
from xdl.utils.prop_limits import VOLUME_PROP_LIMIT, TIME_PROP_LIMIT

# Relative
from .liquid_handling import Transfer
from ..base_step import ChemputerStep
from ..steps_base import CTurnMotor, CHomeMotor, CMove, CMoveMotor
from ...constants import COMMANDUINO_DEVICE
from ...utils.execution import (
    node_in_graph,
    get_modular_motors
)

class MWAddAndTurn(ChemputerStep, AbstractStep):
    """Step for transfering liquid to the modular wheel and rotating it.

    Args:
        from_vessel (str): Vessel to move the liquid from
        volume (float, optional): Volume to transfer. NOTE: 0 to Turn only.
            Defaults to 25 ml, optional): Specifies whether to reverse direction
            of wheel after turning. Defaults to False.
        motor_steps (int, optional): Number of steps required for one full turn
            of the modular wheel motor. Defaults to 3200.
        wait_turn (float, optional): Time to wait (in seconds) before turning
            wheel. Defaults to 0.5.
        wait_reverse (float, optional): Time to wait (in seconds) before
            reversing wheel direction. Implemented only if wait_turn == 0.
            Defaults to 0.5.
    """

    DEFAULT_PROPS = {
        'volume': '25 mL',
        'n_turns': 1,
        'wait_turn': 0.5,
        'wait_reverse': 0.5,
        'aspiration_speed': 10,
        'dispense_speed': 40,
        'move_speed': 40,
        'reverse_first': False,
        'reverse_after': False,
        'turn_first': False,
        'flush': False
    }

    PROP_TYPES = {
        'from_vessel': str,
        'to_vessel': str,
        'volume': float,
        'motor_name': str,
        'n_turns': int,
        'reverse_first': bool,
        'reverse_after': bool,
        'motor_steps': float,
        'turn_first': bool,
        'wait_turn': float,
        'wait_reverse': float,
        'aspiration_speed': float,
        'dispense_speed': float,
        'move_speed': float,
        'flush': bool
    }

    PROP_LIMITS = {
        'volume': VOLUME_PROP_LIMIT,
        'wait_turn': TIME_PROP_LIMIT,
        'wait_reverse': TIME_PROP_LIMIT
    }

    INTERNAL_PROPS = [
        'motor_name', 'motor_steps', 'to_vessel'
    ]

    def __init__(
        self,
        from_vessel: str,
        volume: Optional[float] = 'default',
        n_turns: Optional[int] = 'default',
        reverse_first: Optional[bool] = 'default',
        reverse_after: Optional[bool] = 'default',
        turn_first: Optional[bool] = 'default',
        wait_turn: Optional[float] = 'default',
        wait_reverse: Optional[float] = 'default',
        aspiration_speed: Optional[float] = 'default',
        dispense_speed: Optional[float] = 'default',
        move_speed: Optional[float] = 'default',
        flush: Optional[bool] = 'default',

        # internal props
        motor_name: Optional[str] = None,
        motor_steps: Optional[int] = None,
        to_vessel: Optional[str] = None,
        **kwargs
    ):
        super().__init__(locals())

    def on_prepare_for_execution(self, graph: MultiDiGraph):
        """Prepares the current step for execution.
        Gets/sets/cleans up appropriate items in preparation for exection.

        Args:
            graph (MultiDiGraph): Chemputer Graph to check
        """
        motor_info = get_modular_motors(graph)
        if not self.to_vessel:
            self.to_vessel = motor_info['device_name']
        if not self.motor_name:
            self.motor_name = motor_info['modular_wheel']
        if not self.motor_steps:
            self.motor_steps = motor_info['modular_wheel_increments']

    def get_steps(self) -> List[Step]:
        """Get the list of steps/base steps to execute.

        Returns:
            List[Step]: Steps to execute.
        """

        #  add step
        add_step = Transfer(
            from_vessel=self.from_vessel,
            to_vessel=self.to_vessel,
            volume=self.volume,
            aspiration_speed=self.aspiration_speed,
            dispense_speed=self.dispense_speed,
            move_speed=self.move_speed,
            flush_tubing=self.flush
        )

        #  turn step
        turn_step = CTurnMotor(
            device_name=self.to_vessel,
            motor_name=self.motor_name,
            n_turns=self.n_turns,
            reverse_first=self.reverse_first,
            reverse_after=self.reverse_after,
            wait_turn=self.wait_turn,
            wait_reverse=self.wait_reverse,
            increment=self.motor_steps
        )

        if self.turn_first:
            return [turn_step, add_step]

        return [add_step, turn_step]

    def sanity_checks(self, graph: MultiDiGraph) -> List[SanityCheck]:
        """Gets a list of Sanity checks to perform for the step

        Args:
            graph (MultiDiGraph): Chemputer graph to check

        Returns:
            List[SanityCheck]: List of checks to perform
        """

        return [
            SanityCheck(
                condition=self.from_vessel and node_in_graph(
                    graph, self.from_vessel),
                error_msg="from_vessel must be node in the graph"
            ),
            SanityCheck(
                condition=self.to_vessel and node_in_graph(
                    graph, self.to_vessel),
                error_msg="to_vessel must be node in the graph"
            ),
            SanityCheck(
                condition=(0 <= self.volume < 100),
                error_msg="Volume must be between 0 and 100 mL"
            ),
            SanityCheck(
                condition=self.volume or self.n_turns,
                error_msg=(
                    "must specify either a volume to add or number of turns")
            ),
            SanityCheck(
                condition=self.to_vessel and node_in_graph(
                    graph, self.to_vessel),
                error_msg="to_vessel must be node in graph"
            )
        ]

class HarvestWheel(ChemputerStep, AbstractStep):
    """Harvests sample from The Modular Wheel via The Modular Syringe.

    Args:
        volume (float): volume to harvest.
        to_vessel (str): destination of harvested sample.
        n_turns (int, optional): number of wheel turns to make before harvesting
            sample. Defaults to 0.
        aspiration_speed (float, optional): pump aspiration speed when
            harvesting sample. Defaults to 10 mL / min.
        dispense_speed (float, optional): pump dispense speed when dispensing
            harvested sample to destination. Defaults to 40 mL / min.
        move_speed (float, optional): pump move speed when harvesting sample.
            Defaults to 40 mL / min.

    """
    DEFAULT_PROPS = {
        'n_turns': 0,
        'aspiration_speed': 10,
        'dispense_speed': 40,
        'move_speed': 40
    }

    PROP_TYPES = {
        'n_turns': int,
        'xy_motor': str,
        'z_motor': str,
        'volume': float,
        'to_vessel': str,
        'from_vessel': str,
        'aspiration_speed': float,
        'dispense_speed': float,
        'move_speed': float,
        'xy_step_distance': float,
        'z_step_distance': float,
        'device_name': str,
        'modular_motor': str
    }

    PROP_LIMITS = {
        'volume': VOLUME_PROP_LIMIT
    }

    INTERNAL_PROPS = [
        'from_vessel',
        'xy_motor',
        'z_motor',
        'z_step_distance',
        'xy_step_distance',
        'device_name',
        'modular_motor'
    ]

    def __init__(
        self,
        volume: float,
        to_vessel: str,
        n_turns: Optional[int] = 'default',
        move_speed: Optional[float] = 'default',
        aspiration_speed: Optional[float] = 'default',
        dispense_speed: Optional[float] = 'default',

        #  internal props
        from_vessel: Optional[str] = None,
        xy_motor: Optional[str] = None,
        z_motor: Optional[str] = None,
        z_step_distance: Optional[str] = None,
        xy_step_distance: Optional[str] = None,
        device_name: Optional[str] = None,
        modular_motor: Optional[str] = None,
        **kwargs
    ):
        super().__init__(locals())

    def on_prepare_for_execution(self, graph: MultiDiGraph):
        """Prepares the current step for execution.
        Gets/sets/cleans up appropriate items in preparation for exection.

        Args:
            graph (MultiDiGraph): Chemputer Graph to check
        """

        motors = get_modular_motors(graph=graph)

        if not self.xy_motor:
            self.xy_motor = motors['xy_motor']
            self.xy_step_distance = motors['xy_step_distance']
        if not self.z_motor:
            self.z_motor = motors['z_motor']
            self.z_step_distance = motors['z_step_distance']
        if not self.device_name:
            self.device_name = motors['device_name']
        if not self.modular_motor:
            self.modular_motor = motors['modular_wheel']

        for node, data in graph.nodes(data=True):
            if data['class'] == COMMANDUINO_DEVICE:
                if data['name'] in ['syringe', 'modular_syringe']:
                    self.from_vessel = data['name']

    def get_steps(self) -> List[Step]:
        """Get the list of steps/base steps to execute.

        Returns:
            List[Step]: Steps to execute.
        """

        steps = []

        if not self.modular_motor:
            return steps

        #  home z motor, then xy motor
        homing = [
            CHomeMotor(
                device_name=self.device_name,
                motor_name=self.z_motor
            ),
            CHomeMotor(
                device_name=self.device_name,
                motor_name=self.xy_motor
            )
        ]
        steps.extend(homing)

        #  turn wheel if required
        if self.n_turns > 0:
            steps.append(
                CTurnMotor(
                    device_name=self.device_name,
                    motor_name=self.mod
                )
            )

        #  turn xy motor to harvesting vial
        steps.append(
            CMoveMotor(
                device_name=self.device_name,
                motor_name=self.xy_motor,
                motor_steps=self.xy_step_distance
            )
        )

        #  lower syringe down to harvesting vial
        steps.append(
            CMoveMotor(
                device_name=self.device_name,
                motor_name=self.z_motor,
                motor_steps=self.z_step_distance
            )
        )

        #  harvest from vial
        steps.append(
            CMove(
                volume=self.volume,
                from_vessel=self.from_vessel,
                to_vessel=self.to_vessel,
                move_speed=self.move_speed,
                aspiration_speed=self.aspiration_speed,
                dispense_speed=self.dispense_speed
            )
        )

        #  ensure z and xy motors are homed after harvest
        steps.extend(homing)

        return steps

    def sanity_checks(self, graph: MultiDiGraph) -> List[SanityCheck]:
        """Gets a list of Sanity checks to perform for the step

        Args:
            graph (MultiDiGraph): Chemputer graph to check

        Returns:
            List[SanityCheck]: List of checks to perform
        """

        return [
            SanityCheck(
                condition=self.from_vessel and node_in_graph(
                    graph, self.from_vessel),
                error_msg="from_vessel must be node in the graph"
            ),
            SanityCheck(
                condition=self.to_vessel and node_in_graph(
                    graph, self.to_vessel),
                error_msg="to_vessel must be node in the graph"
            ),
            SanityCheck(
                condition=(0 <= self.volume < 100),
                error_msg="Volume must be between 0 and 100 mL"
            )
        ]
