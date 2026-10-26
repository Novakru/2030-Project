"""
.. module:: steps-base.bubble_sensor
    :platform: Unix, Windows
    :synopsis: Base steps for the Chemputer Bubble Sensor

"""

# std lib
import time
import logging
from typing import Callable, Dict, List, Union

# external
from networkx import MultiDiGraph

# XDL
from xdl.steps.base_steps import AbstractBaseStep, AbstractAsyncStep, Step
from xdl.steps.utils import FTNDuration

# Relative
from ..base_step import ChemputerStep

# For type annotations
if False:
    import Chempiler

class InvokeBubbleSensor(ChemputerStep, AbstractAsyncStep):
    """ Start reading bubble sensor in background.

    Args:
        bubble_sensor (str): Name of the bubble sensor node.
        on_going (Callable): Callback function called during readings obtaining.
    """

    PROP_TYPES = {
        'bubble_sensor': str,
        'on_going': Callable,
        'reading_delay': float,
    }

    DEFAULT_PROPS = {
        'reading_delay': .1,
        'on_going': None,
    }

    def __init__(
            self,
            bubble_sensor: str,
            on_going: Callable = 'default',
            reading_delay: float = 'default',
            **kwargs
    ):
        super().__init__(locals())

        self._should_end = False
        self.readings = []

    def async_execute(
            self,
            platform_controller: 'Chempiler',
            logger: logging.Logger = None,
            level: int = 0,
            step_indexes: List[int] = None,
    ) -> bool:

        self.logger.debug('Starting bubble sensor reading async step <%d>',
                          id(self))

        # Acquiring lock on bubble sensor
        bubble_sensor_object = platform_controller.acquire(
            self.bubble_sensor
        )

        while not self._should_end:
            try:
                reading = bubble_sensor_object.take_reading()
            # TODO needs testing for more precise exception catching
            # This is done to ensure chempiler lock is released
            except Exception as exc:  # pylint: disable=broad-except
                self.logger.error('Exception in bubble reading thread: %s',
                                  exc)
                break
            self.readings.append(reading)

            # Reserved for future use
            # self.on_going(reading)

            time.sleep(self.reading_delay)

        # Releasing chempiler lock
        platform_controller.release(self.bubble_sensor)

        return True

    def reagents_consumed(self, graph: MultiDiGraph) -> Dict[str, float]:
        """ No reagents are consumed during reading bubble sensor. """

        return {}

    def duration(self, graph: MultiDiGraph) -> FTNDuration:
        """ Approximate calculation based on default volume and speed during
            withdrawal. """

        return FTNDuration(.5, 1., 5.)

class EndBubbleSensor(ChemputerStep, AbstractBaseStep):
    """ Utility step to end bubble sensor reading thread.

    Args:
        children (Union[Step, List[Step]]): InvokeBubbleSensor step to end.
        on_finish (Callable): Callback function to execute when step is
            finished. Must accept List (readings) as argument.
    """

    PROP_TYPES = {
        'children': Union[Step, List[Step]],
        'on_finish': Callable,
    }

    def __init__(self, children: Union[Step, List[Step]],
                 on_finish: Callable, **kwargs) -> None:
        super().__init__(locals())

        if not isinstance(children, List):
            self.children = [children]

        self.step = self.children[0]

    def execute(self, platform_controller, logger=None, level=0) -> bool:
        """ Simply kills the Invoke step to terminate reading thread. """

        self.logger.debug('Killing bubble reading step <%d>', id(self.step))

        self.step.kill()
        self.step.thread.join()
        self.on_finish(self.step.readings)

        return True
