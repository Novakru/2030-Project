"""
.. module:: chemobot_steps.base_step
    :platform: Unix, Windows
    :synopsis: Base steps to implement XDL for Chemobot platforms

.. moduleauthor:: Graham Keenan (Cronin Lab 2019)

"""

from logging import Logger
from typing import Optional
from ....steps.base_steps import AbstractBaseStep

class CBTurnWheel(AbstractBaseStep):
    """Turns the wheel on the Chemobot Modular Wheel system

    Inherits:
        AbstractBaseStep: AbstractBaseStep class

    Args:
        n_turns (int): Number of turns to move
    """

    def __init__(self, n_turns: int, **kwargs) -> None:
        super().__init__(locals())

    def execute(
        self, chemobot_mgr, logger: Optional[Logger] = None, level: int = 0
    ) -> None:
        if self.n_turns <= 0:
            return True

        chemobot_mgr.wheel.turn_wheel(self.n_turns)
        return True

class CBDispense(AbstractBaseStep):
    """Dispenses a volume from a given pump

    Inherits:
        AbstractBaseStep: AbstractBaseStep class

    Args:
        pump (str): Name of the pump
        volume (float): Volume to dispense
        in_valve (str): Tricont valve to pull in from (Triconts only -- \
Defaults to 'I')
        out_valve (str): Tricont valve to dispense from (Triconts only -- \
Defaults to 'O')
    """

    def __init__(
        self,
        pump: str,
        volume: float,
        in_valve: str = "I",
        out_valve: str = "O",
        **kwargs
    ) -> None:
        super().__init__(locals())

    def execute(
        self, chemobot_mgr, logger: Optional[Logger] = None, level: int = 0
    ) -> None:
        chemobot_mgr.dispense(
            self.pump, self.volume, self.in_valve, self.out_valve)
        return True

class CBSetStirRate(AbstractBaseStep):
    """Sets the stir rate of the wheel's stirring mechanism

    Inherits:
        AbstractBaseStep: AbstractBaseStep class

    Args:
        stir_rate (int): PWM value

    """
    def __init__(self, stir_rate: int, **kwargs) -> None:
        super().__init__(locals())

    def execute(
        self, chemobot_mgr, logger: Optional[Logger] = None, level: int = 0
    ) -> None:
        chemobot_mgr.set_stir_rate(self.stir_rate)
        return True

class CBWait(AbstractBaseStep):
    """Pause execution until time has elapsed

    Inherits:
        AbstractBaseStep: AbstractBaseStep class

    Args:
        wait_time (float): Wait time in seconds

    """
    def __init__(self, wait_time: float, **kwargs) -> None:
        super().__init__(locals())

    def execute(
        self, chemobot_mgr, logger: Logger = None, level: int = 0
    ) -> None:
        chemobot_mgr.wait(self.wait_time)
        return True
