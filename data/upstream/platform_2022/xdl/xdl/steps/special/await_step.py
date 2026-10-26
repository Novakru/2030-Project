from typing import List
import logging
import time

from ..core import (
    AbstractAsyncStep,
    AbstractAwaitStep,
)
from ..logging import start_executing_step_msg, finished_executing_step_msg


class Await(AbstractAwaitStep):
    """Wait for Async step with given pid to finish executing.

    Args:
        pid (str): pid of :py:class:``Async`` step to wait for.
    """

    PROP_TYPES = {
        'pid': str,
    }

    def __init__(self, pid: str, **kwargs):
        super().__init__(locals())
        self.steps = []

    def execute(
        self,
        async_steps: List[AbstractAsyncStep],
        logger: logging.Logger = None,
        level: int = 0,
        step_indexes: List[int] = None,
    ) -> None:
        # Log step start if it is executed by itself (level == 0), as there will
        # be no other context logging the step start.
        if level == 0:
            logger.info(start_executing_step_msg(self, step_indexes))

        # Await async step with self.pid
        for async_step in async_steps:
            if async_step.pid == self.pid:
                while not async_step.finished:
                    time.sleep(1)
                # Reset async step so it can be used again, for example in
                # Repeat step.
                async_step.finished = False
                break

        # Log step finish
        logger.info(finished_executing_step_msg(self, step_indexes))
        return True

    def locks(self, chempiler):
        return [], [], []
