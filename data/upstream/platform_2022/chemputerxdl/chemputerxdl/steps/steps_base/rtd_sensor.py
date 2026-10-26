"""
Base steps for the Chemputer RTD sensor.
"""

from typing import Callable
from xdl.steps.base_steps import AbstractBaseStep
from ..base_step import ChemputerStep

class ReadRTDSensor(ChemputerStep, AbstractBaseStep):
    """
    Take reading from RTD sensor and send to callback.

    Args:
        rtd_sensor (str): Node name of RTD sensor.
        on_reading (Callable): Callback to send RTD sensor reading to.
    """
    PROP_TYPES = {
        'rtd_sensor': str,
        'on_reading': Callable,
    }

    def __init__(
            self,
            rtd_sensor: str,
            on_reading: Callable,
            **kwargs
    ) -> None:
        super().__init__(locals())

    def execute(self, platform_controller, logger=None, level=0) -> bool:
        """Take reading from RTD sensor and pass to callback."""

        rtd_sensor = platform_controller.acquire(self.rtd_sensor)
        self.on_reading(rtd_sensor.get_temperature())
        platform_controller.release(self.rtd_sensor)

        return True
