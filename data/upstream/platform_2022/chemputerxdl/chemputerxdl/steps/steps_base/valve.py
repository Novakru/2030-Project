"""
.. module:: steps_base.valve
    :platforms: Unix, Windows
    :synopsis: Base steps for Chemputer Valves

"""

from typing import Tuple, List

# XDL
from xdl.steps.base_steps import AbstractBaseStep
from xdl.utils.prop_limits import PropLimit

# Relative
from ..base_step import ChemputerStep

class CValveMoveToPosition(ChemputerStep, AbstractBaseStep):
    """Move valve to given position.

    Args:
        valve_name (str): Node name of the valve to move.
        position (int): Position to move valve to.
    """

    PROP_TYPES = {
        'valve_name': str,
        'position': int
    }

    PROP_LIMITS = {
        'position': PropLimit(
            hint='Expecting int from 0-5, e.g. "0", "5"',
            enum=['0', '1', '2', '3', '4', '5'],
            default='0'
        )
    }

    def __init__(self, valve_name: str, position: int, **kwargs) -> None:
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

        return [self.valve_name], [], []

    def execute(self, chempiler, logger=None, level=0) -> bool:
        """Executes the XDL step.

        Args:
            chempiler (Chempiler): Chempiler object
            logger (Logger, optional): Logging object. Defaults to None.
            level (int, optional): Logging level. Defaults to 0.

        Returns:
            bool: Step executed successfully.
        """
        valve = chempiler.acquire(self.valve_name)
        valve.move_to_position(self.position)
        chempiler.release(self.valve_name)
        return True
