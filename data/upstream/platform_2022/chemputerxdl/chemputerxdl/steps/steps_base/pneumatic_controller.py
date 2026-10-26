"""
.. module:: steps_base.pneumatic_controller
    :platforms: Unix, Windows
    :synopsis: Base steps for controlling the Chemputer Pneumatic Controller

"""

from typing import Tuple, List

# XDL
from xdl.steps.base_steps import AbstractBaseStep

# Relative
from ..base_step import ChemputerStep
from ...utils.prop_limits import (
    PNEUMATIC_CONTROLLER_PORT_PROP_LIMIT,
    PNEUMATIC_CONTROLLER_PRESSURE_PROP_LIMIT,
)

class CSwitchVacuum(ChemputerStep, AbstractBaseStep):
    """Using PneumaticController switch given port to vacuum supply.

    Args:
        pneumatic_controller (str): Name of PneumaticController node.
        port (int): Port of PneumaticController to supply vacuum from.
    """

    PROP_TYPES = {
        'pneumatic_controller': str,
        'port': int
    }

    PROP_LIMITS = {
        'port': PNEUMATIC_CONTROLLER_PORT_PROP_LIMIT,
    }

    def __init__(self, pneumatic_controller: str, port: int, **kwargs):
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

        return [self.pneumatic_controller], [], []

    def execute(self, chempiler, logger=None, level=0) -> bool:
        """Executes the XDL step.

        Args:
            chempiler (Chempiler): Chempiler object
            logger (Logger, optional): Logging object. Defaults to None.
            level (int, optional): Logging level. Defaults to 0.

        Returns:
            bool: Step executed successfully.
        """

        pneumatic_controller = chempiler.acquire(self.pneumatic_controller)
        pneumatic_controller.switch_vacuum(self.port)
        chempiler.release(self.pneumatic_controller)
        return True

class CSwitchArgon(ChemputerStep, AbstractBaseStep):
    """Using PneumaticController switch given port to argon supply.

    Args:
        pneumatic_controller (str): Name of PneumaticController node.
        port (int): Port of PneumaticController to supply argon from.
        pressure (str): 'low' or 'high'. Defaults to 'low'.
    """

    PROP_TYPES = {
        'pneumatic_controller': str,
        'port': int,
        'pressure': str
    }

    PROP_LIMITS = {
        'port': PNEUMATIC_CONTROLLER_PORT_PROP_LIMIT,
        'pressure': PNEUMATIC_CONTROLLER_PRESSURE_PROP_LIMIT
    }

    def __init__(
        self,
        pneumatic_controller: str,
        port: int,
        pressure: str = 'low',
        **kwargs
    ) -> None:
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

        return [self.pneumatic_controller], [], []

    def execute(self, chempiler, logger=None, level=0) -> bool:
        """Executes the XDL step.

        Args:
            chempiler (Chempiler): Chempiler object
            logger (Logger, optional): Logging object. Defaults to None.
            level (int, optional): Logging level. Defaults to 0.

        Returns:
            bool: Step executed successfully.
        """
        pneumatic_controller = chempiler.acquire(self.pneumatic_controller)
        pneumatic_controller.switch_argon(self.port, pressure=self.pressure)
        chempiler.release(self.pneumatic_controller)
        return True
