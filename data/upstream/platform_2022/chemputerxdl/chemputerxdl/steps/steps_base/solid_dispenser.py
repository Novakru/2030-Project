"""
.. module steps_base.solid_dispenser
    :platforms: Unix, Windows
    :synopsis: Base steps for the Solid Dispenser in the ChemputerAPI
"""

# External
from networkx import MultiDiGraph
from typing import Optional, Tuple, List

# XDL
from xdl.steps.utils import FTNDuration
from xdl.utils.prop_limits import PropLimit
from xdl.steps.base_steps import AbstractBaseStep

# Relative
from ..base_step import ChemputerStep

class CDispenseSolid(ChemputerStep, AbstractBaseStep):
    """Dispenses a solid using the Solid Dispenser from a given position.

    Args:
        device_name (str): Name of the device representing the dispenser.
        position (int): Number of positions the dispensing wheel will move.
        rpm (int): Speed of the motor in RPM.
        driver (int): Motor driver to use dependent on board.
    """

    DEFAULT_PROPS = {
        'rpm': 100,
        'driver': 1
    }

    PROP_TYPES = {
        'device_name': str,
        'position': int,
        'driver': int,
        'rpm': int,
        'motor_driver': int
    }

    PROP_LIMITS = {
        'driver': PropLimit(
            enum=['1', '2'],
            default='1'
        ),
        'rpm': PropLimit(
            enum=[str(i) for i in range(1, 601)]
        )
    }

    def __init__(
        self,
        device_name: str,
        position: int,
        rpm: Optional[int] = 'default',
        driver: Optional[int] = 'default',
        **kwargs
    ):
        super().__init__(locals())

    def locks(self, chempiler) -> Tuple[List[str], List[str], List[str]]:
        """Returns a series of locked nodes used by the Paralleliser

        Args:
            chempiler (Chempiler): Chempiler object

        Returns:
            Tuple[List[str], List[str], List[str]]: Locked nodes in the order:
                                    1.) Current Locks -- Currently locked
                                    2.) Ongoing Locks -- Continually locked
                                    3.) Unlocks -- Unlocked

        """
        return [self.device_name], [], []

    def execute(self, chempiler, logger=None, level=0) -> bool:
        """Executes the XDL step

        Args:
            chempiler (Chempiler): Chempiler object
            logger (Logger, optional): Logging object. Defaults to None.
            level (int, optional): Logging level. Defaults to 0.

        Returns:
            bool: Step executed successfully
        """

        device = chempiler.acquire(self.device_name)
        self.logger.info(f"TYPE: {type(device)}")
        device.dispense_pos(self.position, self.rpm, self.driver)
        chempiler.release(self.device_name)
        return True

    def duration(self, graph: MultiDiGraph) -> FTNDuration:
        """Calculates the duration of the step

        Args:
            graph (MultiDiGraph): Graph to search

        Returns:
            FTNDuration: Duration of the step
        """

        return FTNDuration(
            3, 5, 7
        )
