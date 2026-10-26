# Std
from typing import Any
import logging
import time

# Other
from networkx import MultiDiGraph

# Relative
from ..core import AbstractBaseStep
from ..utils import FTNDuration
from ...utils.prop_limits import TIME_PROP_LIMIT


class Wait(AbstractBaseStep):
    """Wait for given time.

    Args:
        time (int): Time in seconds
    """

    PROP_TYPES = {
        'time': float,
    }

    PROP_LIMITS = {
        'time': TIME_PROP_LIMIT,
    }

    def __init__(self, time: float, **kwargs) -> None:
        super().__init__(locals())

    def execute(
        self,
        platform_controller: Any,
        logger: logging.Logger = None,
        level: int = 0
    ) -> bool:
        # Don't wait if platform_controller is in simulation mode.
        if (hasattr(platform_controller, 'simulation')
                and platform_controller.simulation is True):
            return True

        time.sleep(self.time)
        return True

    def duration(self, graph: MultiDiGraph) -> FTNDuration:
        return FTNDuration(self.time, self.time, self.time)
