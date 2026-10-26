"""
.. module:: steps-base.conductivity_sensor
    :platform: Unix, Windows
    :synopsis: Base steps for the Chemputer Conductivity Sensor

"""

from typing import Callable, Tuple, List

# XDL
from xdl.steps.base_steps import AbstractBaseStep

# Relative
from ..base_step import ChemputerStep

class ReadConductivitySensor(ChemputerStep, AbstractBaseStep):
    """Reads the value on a conductivity sensor

    Args:
        sensor (str): Name of the sensor attached to the Chemputer
        on_reading (Callable): Callback fn when reading hte sensor
    """

    PROP_TYPES = {
        'sensor': str,
        'on_reading': Callable  # using typing because no built-in func type
    }

    def __init__(self, sensor: str, on_reading: Callable, **kwargs):
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

        return [self.sensor], [], []

    def execute(self, chempiler, logger=None, level=0) -> bool:
        """Executes the XDL step.

        Args:
            chempiler (Chempiler): Chempiler object
            logger (Logger, optional): Logging object. Defaults to None.
            level (int, optional): Logging level. Defaults to 0.

        Returns:
            bool: Step executed successfully.
        """

        if chempiler.simulation:
            self.on_reading(-1)
        else:
            sensor = chempiler.acquire(self.sensor)
            self.on_reading(sensor.take_reading_combined())
            chempiler.release(self.sensor)

        return True
