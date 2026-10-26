"""
.. module:: steps_base.commanduino_labware
    :platforms: Unix, Windows
    :synopsis: Base steps for CommanduinoLabware in context of the Chemputer

"""
import time

from typing import Optional, Tuple, List
from networkx import MultiDiGraph

# XDL
from xdl.steps.base_steps import AbstractBaseStep
from xdl.steps.utils import FTNDuration
from xdl.utils.prop_limits import TIME_PROP_LIMIT, PropLimit

# Relative
from ..base_step import ChemputerStep
from ...utils.prop_limits import INT_0_255_PROP_LIMIT

class CTurnMotor(ChemputerStep, AbstractBaseStep):
    """Turns a motor on a Commanduino Labware device

    Args:
        device_name (str): Name of the node representing the labware device
        motor_name (str): Name of the motor on the device
        n_turns (int): How many turns to make the motor perform
        increment (int): NUmber of steps which represent 1 single turn
        reverse_first (bool, optional): specifies whether to reverse motor
            direction before turn. Defaults to False.
        reverse_after (bool, optional): specifies whether to reverse motor
            direction after turn. Defaults to False.
        wait_turn (float, optional): time to wait before turning wheel. A short
            wait is useful to avoid spilling sample when this step is a substep
            of MWAddAndTurn or RepeatCleanMW, or used in combination with
            Transfer
        wait_reverse (float, optional): time to wait after reversing
            wheel direction. Avoid jerking the wheel. Only implemented when
            wait_turn == 0.
    """

    DEFAULT_PROPS = {
        'n_turns': 1,
        'increment': 3200,
        'reverse_first': False,
        'reverse_after': True,
        'wait_turn': 0.5,
        'wait_reverse': 0.5
    }

    PROP_TYPES = {
        'device_name': str,
        'motor_name': str,
        'n_turns': int,
        'increment': int,
        'reverse_first': bool,
        'reverse_after': bool,
        'wait_turn': float,
        'wait_reverse': float
    }

    PROP_LIMITS = {
        'wait_turn': TIME_PROP_LIMIT,
        'wait_reverse': TIME_PROP_LIMIT
    }

    def __init__(
        self,
        device_name: str,
        motor_name: str,
        n_turns: int = 'default',
        increment: Optional[int] = 'default',
        reverse_first: Optional[bool] = 'default',
        reverse_after: Optional[bool] = 'default',
        wait_turn: Optional[float] = 'default',
        wait_reverse: Optional[float] = 'default',
        **kwargs
    ):
        super().__init__(locals())

    def locks(self, chempiler) -> Tuple[List[str], List[str], List[str]]:
        """Returns a series of locked nodes used by the Paralleliser.

        Args:
            chempiler (Chempiler): Chempiler object

        Returns:
            Tuple[List[str], List[str], List[str]]: Locked nodes in the order:
                                    1.) Current Locks -- Currently locked
                                    2.) Ongoing locks -- Continually locked
                                    3.) Unlocks -- Unlocked
        """

        return [self.device_name], [], []

    def execute(self, chempiler, logger=None, level=0) -> bool:
        """Executes the XDL step

        Args:
            chempiler (Chempiler): Chempiler object.
            logger (Logger, optional): Logging object. Defaults to None.
            level (int, optional): Logging level. Defaults to 0.

        Returns:
            bool: Step executed successfully.
        """

        # Avoid sleeping during simulations as it wastes time
        wait_reverse = self.wait_reverse
        wait_turn = self.wait_turn
        if chempiler.simulation:
            wait_reverse = 0
            wait_turn = 0

        device = chempiler.acquire(self.device_name)

        #  reverse motor direction before turn if required
        if self.reverse_first:
            device.reverse_motor_direction(motor=self.motor_name)

            #  1 second wait after reverse to avoid the wheel jerking!!!
            if self.wait_reverse > 0:
                if self.wait_turn == 0:
                    time.sleep(wait_reverse)

        #  wait before turning wheel to avoid sample spillage
        time.sleep(wait_turn)

        device.turn_motor(
            self.motor_name, n_turns=self.n_turns, increment=self.increment
        )

        #  reverse motor direction after turn if required
        if self.reverse_after:
            device.reverse_motor_direction(motor=self.motor_name)

        chempiler.release(self.device_name)

        return True

    def duration(self, graph: MultiDiGraph) -> FTNDuration:
        """Calculates duration of the step

        Args:
            graph (MultiDiGraph): Graph to search

        Returns:
            FTNDuration: Duration of step
        """

        return FTNDuration(
            self.n_turns * 0.1, self.n_turns * 1.5, self.n_turns * 3
        )

class CMoveMotor(ChemputerStep, AbstractBaseStep):
    """Moves a motor a number of steps

    Args:
        device_name (str): Name of the node representing the labware device
        motor_name (str): Name of the motor on the device
        steps (int): Number of steps to move
    """

    PROP_TYPES = {
        'device_name': str,
        'motor_name': str,
        'motor_steps': int
    }

    def __init__(
        self,
        device_name: str,
        motor_name: str,
        motor_steps: int,
        **kwargs
    ):
        super().__init__(locals())

    def locks(self, chempiler) -> Tuple[List[str], List[str], List[str]]:
        """Returns a series of locked nodes used by the Paralleliser.

        Args:
            chempiler (Chempiler): Chempiler object

        Returns:
            Tuple[List[str], List[str], List[str]]: Locked nodes in the order:
                                    1.) Current Locks -- Currently locked
                                    2.) Ongoing locks -- Continually locked
                                    3.) Unlocks -- Unlocked
        """

        return [self.device_name], [], []

    def execute(self, chempiler, logger=None, level=0) -> bool:
        """Executes the XDL step

        Args:
            chempiler (Chempiler): Chempiler object.
            logger (Logger, optional): Logging object. Defaults to None.
            level (int, optional): Logging level. Defaults to 0.

        Returns:
            bool: Step executed successfully.
        """

        device = chempiler.acquire(self.device_name)
        device.move_motor(self.motor_name, self.motor_steps)
        chempiler.release(self.device_name)
        return True

    def duration(self, graph: MultiDiGraph) -> FTNDuration:
        """Calculates duration of the step

        Args:
            graph (MultiDiGraph): Graph to search

        Returns:
            FTNDuration: Duration of step
        """

        # Assumes Nema17 - Not that accurate
        # Could do some calculation with steps to calculate time but this is
        # a good ballpark figure
        # TODO::More robust calculation
        timescale = self.motor_steps / 6400

        return FTNDuration(
            timescale * 0.75, timescale, timescale * 1.5
        )

class CMoveMotorToPosition(ChemputerStep, AbstractBaseStep):
    """Moves a motor to a given position, in steps

    Args:
        device_name (str): Name of the node representing the labware device
        motor_name (str): Name of the motor on the device
        position (int): POsition to move the motor to
    """

    PROP_TYPES = {
        'device_name': str,
        'motor_name': str,
        'position': int
    }

    def __init__(
            self, device_name: str, motor_name: str, position: int, **kwargs):
        super().__init__(locals())

    def locks(self, chempiler) -> Tuple[List[str], List[str], List[str]]:
        """Returns a series of locked nodes used by the Paralleliser.

        Args:
            chempiler (Chempiler): Chempiler object

        Returns:
            Tuple[List[str], List[str], List[str]]: Locked nodes in the order:
                                    1.) Current Locks -- Currently locked
                                    2.) Ongoing locks -- Continually locked
                                    3.) UnlocksNone, level=0) -> bool:

        Returns:
            bool: Step executed successfully.
        """

        device = chempiler.acquire(self.device_name)
        device.move_motor_to_position(self.motor_name, self.position)
        chempiler.release(self.device_name)
        return True

    def duration(self, graph: MultiDiGraph) -> FTNDuration:
        """Calculates duration of the step

        Args:
            graph (MultiDiGraph): Graph to search

        Returns:
            FTNDuration: Duration of step
        """

        # Assumes Nema17 - Not that accurate
        # Could do some calculation with steps to calculate time but this is
        # a good ballpark figure
        # TODO::More robust calculation
        timescale = self.position / 6400

        return FTNDuration(
            timescale * 0.75, timescale, timescale * 1.5
        )

class CHomeMotor(ChemputerStep, AbstractBaseStep):
    """Moves a motor to its home position.
    Requires a home switch to be present.

    Args:
        device_name (str): Name of the node representing the labware device.
        motor_name (str): Name of the motor on the device
    """

    PROP_TYPES = {
        'device_name': str,
        'motor_name': str
    }

    def __init__(self, device_name: str, motor_name: str, **kwargs):
        super().__init__(locals())

    def locks(self, chempiler) -> Tuple[List[str], List[str], List[str]]:
        """Returns a series of locked nodes used by the Paralleliser.

        Args:
            chempiler (Chempiler): Chempiler object

        Returns:
            Tuple[List[str], List[str], List[str]]: Locked nodes in the order:
                                    1.) Current Locks -- Currently locked
                                    2.) Ongoing locks -- Continually locked
                                    3.) Unlocks -- Unlocked
        """

        return [self.device_name], [], []

    def execute(self, chempiler, logger=None, level=0) -> bool:
        """Executes the XDL step.

        Args:
            chempiler (Chempiler): Chempiler object
            logger (Logger, optional): Logging object. Defaults to None.
            level (int, optional): Logging level. Defaults to 0.

        Returns:
            bool: Step executed successfully.
        """
        device = chempiler.acquire(self.device_name)
        device.home_motor(self.motor_name)
        chempiler.release(self.device_name)
        return True

    def duration(self, graph: MultiDiGraph) -> FTNDuration:
        """Calculates duration of the step

        Args:
            graph (MultiDiGraph): Graph to search

        Returns:
            FTNDuration: Duration of step
        """

        # Homing motor duration varies widely dependent on the type of motor
        # used, these are rough ballpark figures based on experience
        # TODO::More robust calculation

        min_duration, likely_duration = 1, 3
        return FTNDuration(
            min_duration, likely_duration, likely_duration * 2
        )

class CRunMotor(ChemputerStep, AbstractBaseStep):
    """Runs a motor for a given period of time, in seconds

    Args:
        device_name (str): Name of the node representing the labware device
        motor_name (str): Name of the motor on the device
        timescale (int): Length of time to run for, in seconds
        increment (int, optional): Increment in steps. Defaults to 8000.
    """

    DEFAULT_PROPS = {
        'increment': 8000
    }

    PROP_TYPES = {
        'device_name': str,
        'motor_name': str,
        'timescale': int,
        'increment': int
    }

    PROP_LIMITS = {
        'timescale': TIME_PROP_LIMIT,
    }

    def __init__(
        self,
        device_name: str,
        motor_name: str,
        timescale: int,
        increment: Optional[int] = 'default',
        **kwargs
    ):
        super().__init__(locals())

    def locks(self, chempiler) -> Tuple[List[str], List[str], List[str]]:
        """Returns a series of locked nodes used by the Paralleliser.

        Args:
            chempiler (Chempiler): Chempiler object

        Returns:
            Tuple[List[str], List[str], List[str]]: Locked nodes in the order:
                                    1.) Current Locks -- Currently locked
                                    2.) Ongoing locks -- Continually locked
                                    3.) Unlocks -- Unlocked
        """

        return [self.device_name], [], []

    def execute(self, chempiler, logger=None, level=0) -> bool:
        """Executes the XDL step.

        Args:
            chempiler (Chempiler): Chempiler object
            logger (Logger, optional): Logging object. Defaults to None.
            level (int, optional): Logging level. Defaults to 0.

        Returns:
            bool: Step executed successfully.
        """
        device = chempiler.acquire(self.device_name)
        device.run_motor(
            self.motor_name,
            self.timescale,
            increment=self.increment
        )
        chempiler.release(self.device_name)
        return True

    def duration(self, graph: MultiDiGraph) -> FTNDuration:
        """Calculates duration of the step

        Args:
            graph (MultiDiGraph): Graph to search

        Returns:
            FTNDuration: Duration of step
        """

        return FTNDuration(
            self.tiemscale, self.timescale, self.timescale * 1.5
        )

class CSetPin(ChemputerStep, AbstractBaseStep):
    """Sets the value of a digital pin to HIGH or LOW state, dependent on level

    Args:
        device_name (str): Name of the node representing the labware device.
        pin_name (str): Name of the pin on the device.
        level (int, optional): Level to set, either 0 or 1. Defaults to 0.
    """

    DEFAULT_PROPS = {
        'level': 0
    }

    PROP_TYPES = {
        'device_name': str,
        'pin_name': str,
        'level': int
    }

    PROP_LIMITS = {
        'level': PropLimit(
            enum=['0', '1'],
            default='0'
        ),
    }

    def __init__(
        self,
        device_name: str,
        pin_name: str,
        level: Optional[int] = 'default',
        **kwargs
    ):
        super().__init__(locals())

    def locks(self, chempiler) -> Tuple[List[str], List[str], List[str]]:
        """Returns a series of locked nodes used by the Paralleliser.

        Args:
            chempiler (Chempiler): Chempiler object

        Returns:
            Tuple[List[str], List[str], List[str]]: Locked nodes in the order:
                                    1.) Current Locks -- Currently locked
                                    2.) Ongoing locks -- Continually locked
                                    3.) Unlocks -- Unlocked
        """

        return [self.device_name], [], []

    def execute(self, chempiler, logger=None, level=0) -> bool:
        """Executes the XDL step.

        Args:
            chempiler (Chempiler): Chempiler object
            logger (Logger, optional): Logging object. Defaults to None.
            level (int, optional): Logging level. Defaults to 0.

        Returns:
            bool: Step executed successfully.
        """
        device = chempiler.acquire(self.device_name)
        device.set_pin(self.pin_name, level=self.level)
        chempiler.release(self.device_name)
        return True

class CSetPinPWM(ChemputerStep, AbstractBaseStep):
    """Sets the PWm value of an analog pin between 0 and 255.

    Args:
        device_name (str): Name of the node representing the labware device.
        pin_name (str): Name of the pin on the device
        value (int, optional): PWM value between 0 and 255. Defaults to 0.
    """

    DEFAULT_PROPS = {
        'value': 0
    }

    PROP_TYPES = {
        'device_name': str,
        'pin_name': str,
        'value': int
    }

    PROP_LIMITS = {
        'value': INT_0_255_PROP_LIMIT,
    }

    def __init__(
        self,
        device_name: str,
        pin_name: str,
        value: Optional[int] = 'default',
        **kwargs
    ):
        super().__init__(locals())

    def locks(self, chempiler) -> Tuple[List[str], List[str], List[str]]:
        """Returns a series of locked nodes used by the Paralleliser.

        Args:
            chempiler (Chempiler): Chempiler object

        Returns:
            Tuple[List[str], List[str], List[str]]: Locked nodes in the order:
                                    1.) Current Locks -- Currently locked
                                    2.) Ongoing locks -- Continually locked
                                    3.) Unlocks -- Unlocked
        """
        return [self.device_name], [], []

    def execute(self, chempiler, logger=None, level=0) -> bool:
        """Executes the XDL step.

        Args:
            chempiler (Chempiler): Chempiler object
            logger (Logger, optional): Logging object. Defaults to None.
            level (int, optional): Logging level. Defaults to 0.

        Returns:
            bool: Step executed successfully.
        """

        device = chempiler.acquire(self.device_name)
        device.set_pin_pwm(self.pin_name, value=self.value)
        chempiler.release(self.device_name)
        return True

class CReadPin(ChemputerStep, AbstractBaseStep):
    """Reads the current state of a digital pin. HIGH or LOW.

    Args:
        device_name (str): Name of the node representing the labware device.
        pin_name (str): Name of the pin on the device.
    """

    PROP_TYPES = {
        'device_name': str,
        'pin_name': str
    }

    def __init__(self, device_name: str, pin_name: str, **kwargs):
        super().__init__(locals())

    def locks(self, chempiler) -> Tuple[List[str], List[str], List[str]]:
        """Returns a series of locked nodes used by the Paralleliser.

        Args:
            chempiler (Chempiler): Chempiler object

        Returns:
            Tuple[List[str], List[str], List[str]]: Locked nodes in the order:
                                    1.) Current Locks -- Currently locked
                                    2.) Ongoing locks -- Continually locked
                                    3.) Unlocks -- Unlocked
        """

        return [self.device_name], [], []

    def execute(self, chempiler, logger=None, level=0) -> bool:
        """Executes the XDL step.

        Args:
            chempiler (Chempiler): Chempiler object
            logger (Logger, optional): Logging object. Defaults to None.
            level (int, optional): Logging level. Defaults to 0.

        Returns:
            bool: Step executed successfully.
        """

        device = chempiler.acquire(self.device_name)
        device.read_pin(self.pin_name)
        chempiler.release(self.device_name)
        return True

class CReadPinPWM(ChemputerStep, AbstractBaseStep):
    """Reads the current PWM value of an analog pin. Between 0 and 255.

    Args:
        device_name (str): Name of the node representing the labware device.
        pin_name (str): Name of the pin on the device
    """

    PROP_TYPES = {
        'device_name': str,
        'pin_name': str
    }

    def __init__(self, device_name: str, pin_name: str, **kwargs):
        super().__init__(locals())

    def locks(self, chempiler) -> Tuple[List[str], List[str], List[str]]:
        """Returns a series of locked nodes used by the Paralleliser.

        Args:
            chempiler (Chempiler): Chempiler object

        Returns:
            Tuple[List[str], List[str], List[str]]: Locked nodes in the order:
                                    1.) Current Locks -- Currently locked
                                    2.) Ongoing locks -- Continually locked
                                    3.) Unlocks -- Unlocked
        """

        return [self.device_name], [], []

    def execute(self, chempiler, logger=None, level=0) -> bool:
        """Executes the XDL step.

        Args:
            chempiler (Chempiler): Chempiler object
            logger (Logger, optional): Logging object. Defaults to None.
            level (int, optional): Logging level. Defaults to 0.

        Returns:
            bool: Step executed successfully.
        """

        device = chempiler.acquire(self.device_name)
        device.read_pin_pwm(self.pin_name)
        chempiler.release(self.device_name)
        return True
