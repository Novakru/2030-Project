# Std
from typing import List, Dict, Any
import logging
import threading
from abc import abstractmethod

# Other
from networkx import MultiDiGraph

# Relative
from .step import Step
from .abstract_base_step import AbstractBaseStep
from ..utils import FTNDuration

class AbstractAsyncStep(Step):
    """For executing code asynchronously. Can only be used programmatically,
    no way of encoding this in XDL files.

    ``async_execute`` method is executed asynchronously when this step executes.
    Recommended use is to have callback functions in properties when making
    subclasses.

    Args:
        param_dict (Dict[str, Any]): Step properties dict to initialize step
            with.
    """
    def __init__(self, param_dict: Dict[str, Any]) -> None:
        super().__init__(param_dict)
        self._should_end = False

    def execute(
        self,
        platform_controller: Any,
        logger: logging.Logger = None,
        level: int = 0,
        async_steps: List[str] = [],
        step_indexes: List[int] = None,
    ) -> bool:
        """Execute step in new thread.

        Args:
            platform_controller (Any): Platform controller to execute step with.
            logger (logging.Logger): Logger for logging execution info.
            level (int): Level of execution recursion.
            async_steps (List[str]): List of currently executing async step
                pids.
            step_indexes (List[int]): Indexes into steps list and substeps
                lists.

        Returns:
            bool: ``True`` if execution should continue, ``False`` if execution
            should stop.
        """
        self.thread = threading.Thread(
            target=self.async_execute, args=(
                platform_controller, logger, level, step_indexes))
        self.thread.start()
        return True

    @abstractmethod
    def async_execute(
        self, platform_controller: Any,
        logger: logging.Logger = None,
        level: int = 0,
        step_indexes: List[int] = None,
    ) -> bool:
        """Abstract method. Should contain the execution logic that will be
        executed in a separate thread. Equivalent to
        :py:meth:`AbstractBaseStep.execute`, and similarly should return
        ``True`` if the procedure should continue after the step has finished
        executing and ``False`` if the procedure should break after the step has
        finished executing.

        Not called execute like ``AbstractBaseStep`` to keep ``step.execute``
        logic in other places consistent and simple.

        Args:
            platform_controller (Any): Platform controller to execute step with.
            logger (logging.Logger): Logger for logging execution info.

        Returns:
            bool: ``True`` if execution should continue, ``False`` if execution
            should stop.
        """
        return True

    def kill(self) -> None:
        """Flick :py:attr:`self._should_end` killswitch to let
        :py:meth:`async_execute` know that it should return to allow the thread
        to join. This relies on ``async_execute`` having been implemented in a
        way that takes notice of this variable.
        """
        self._should_end = True

    def reagents_consumed(self, graph: MultiDiGraph) -> Dict[str, float]:
        """Return dictionary of reagents and volumes consumed in mL like this:
        ``{ reagent: volume... }``. Can be overridden otherwise just recursively
        adds up volumes used by base steps.

        Args:
            graph (MultiDiGraph): Graph to use when calculating volumes of
                reagents consumed by step.

        Returns:
            Dict[str, float]: Dict of reagents volumes consumed by step in
            format ``{reagent_id: reagent_volume...}``.
        """
        reagents_consumed = {}
        # Get reagents consumed from children (Async step)
        for substep in self.children:
            step_reagents_consumed = substep.reagents_consumed(graph)
            for reagent, volume in step_reagents_consumed.items():
                if reagent in reagents_consumed:
                    reagents_consumed[reagent] += volume
                else:
                    reagents_consumed[reagent] = volume
        return reagents_consumed

    def duration(self, graph: MultiDiGraph) -> FTNDuration:
        """Return duration of child steps (Async step).

        Args:
            graph (MultiDiGraph): Graph to use when calculating step duration.

        Returns:
            FTNDuration: Estimated duration of step in seconds.
        """
        duration = FTNDuration(0, 0, 0)
        for step in self.children:
            duration += step.duration(graph)
        return duration

class AbstractAwaitStep(AbstractBaseStep):
    """
    Abstract step class to control corresponding asynchronously executed
    steps.

    Args:
        parameters (Dict[str, Any]): Step properties for initialization.
    """

    def __init__(self, parameters: Dict[str, Any]) -> None:
        super().__init__(parameters)

    @abstractmethod
    def execute(
        self,
        async_steps: List[AbstractAsyncStep],
        logger: logging.Logger = None,
        level: int = 0,
        step_indexes: List[int] = None,
    ) -> bool:
        """Core method to execute the step.

        As an abstract await step will just kill the corresponding asynchronous
        step, but other things could be added on top.

        Args:
            async_steps (List[AbstractAsyncStep]): List of all asynchronous
                steps started before the current step is executed.
        """
