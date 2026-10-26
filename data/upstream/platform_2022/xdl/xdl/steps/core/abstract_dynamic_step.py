# Std
from typing import List, Dict, Any
import logging
import copy
from abc import abstractmethod

# Other
from networkx import MultiDiGraph

# Relative
from .step import Step
from .abstract_async_step import AbstractAsyncStep
from ..logging import start_executing_step_msg, finished_executing_step_msg
from ..utils import FTNDuration
from ...utils.graph import get_graph
from ...utils.logging import get_logger, log_duration
from ...errors import (
    XDLError,
)
if False:
    from ...execution import AbstractXDLExecutor


class AbstractDynamicStep(Step):
    """Step for containing dynamic experiments in which feedback from analytical
    equipment controls the flow of the experiment.

    Provides abstract methods :py:meth:`on_start`, :py:meth:`on_continue` and
    :py:meth:`on_finish` that each return lists of steps to be performed at
    different stages of the experiment. :py:meth:`on_continue` is called
    repeatedly until it returns an empty list.

    What steps are to be returned should be decided base on the state attribute.
    The state can be updated from any of the three lifecycle methods or from
    :py:class:`AbstractAsyncStep` callback functions.

    Args:
        param_dict (Dict[str, Any]): Step properties dict to initialize step
            with.
    """
    def __init__(self, param_dict: Dict[str, Any]) -> None:
        super().__init__(param_dict)
        self.state = {}
        self.async_steps = []
        self.steps = []

        # None instead of empty list so that you can tell if its been
        # intialized or not. Start block can just be [].
        self.start_block = None
        self.started = False

    @abstractmethod
    def on_start(self) -> List[Step]:
        """Returns list of steps to be executed once at start of step.

        Returns:
            List[Step]: List of  steps to be executed once at start of step.
        """
        return []

    @abstractmethod
    def on_continue(self) -> List[Step]:
        """Returns list of steps to be executed in main loop of step, after
        on_start and before on_finish. Is called repeatedly until empty list is
        returned at which point the steps returned by on_finish are executed
        and the step ends.

        Returns:
            List[Step]: List of steps to execute in main loop based on
                self.state.
        """
        return []

    @abstractmethod
    def on_finish(self) -> List[Step]:
        """Returns list of steps to be executed once at end of step.

        Returns:
            List[Step]: List of steps to be executed once at end of step.
        """
        return []

    def reset(self) -> None:
        """Reset state of step. Should be overridden but doesn't have to be."""
        return

    def resume(
        self,
        platform_controller: Any,
        logger: logging.Logger = None,
        level: int = 0
    ) -> None:
        """Resume execution after a pause.

        Args:
            platform_controller (Any): Platform controller to execute step with.
            logger (logging.Logger): Logger to log execution info with.
            level (int): Recursion level of step execution.
        """
        self.started = False  # Hack to avoid reset.
        self.start_block = []  # Go straight to on_continue
        self.execute(platform_controller, logger=logger, level=level)

    def _post_finish(self) -> None:
        """Called after steps returned by :py:meth:`on_finish` have finished
        executing to try to join all threads.
        """
        for async_step in self.async_steps:
            async_step.kill()

    def prepare_for_execution(
            self, graph: MultiDiGraph, executor: 'AbstractXDLExecutor') -> None:
        """Prepare step for execution.

        Args:
            graph (MultiDiGraph): Graph to use when preparing step for
                execution.
            executor (AbstractXDLExecutor): Executor to compile
                :py:attr:`start_block` with.
        """
        self.executor = executor
        self.graph = graph
        self.on_prepare_for_execution(get_graph(graph))
        self.start_block = self.on_start()
        self.executor.prepare_block_for_execution(self.graph, self.start_block)

    def execute(
        self,
        platform_controller: Any,
        logger: logging.Logger = None,
        level: int = 0,
        step_indexes: List[int] = None,
    ) -> None:
        """Execute step lifecycle. :py:meth:`on_start`, followed by
        :py:meth:`on_continue` repeatedly until an empty list is returned,
        followed by :py:meth:`on_finish`, after which all threads are joined as
        fast as possible.

        Args:
            platform_controller (Any): Platform controller object to use for
                executing steps.
            logger (Logger): Logger object.
            level (int): Level of recursion in step execution.
            step_indexes (List[int]): Indexes into steps list and substeps
                lists.

        Returns:
            bool: ``True`` if execution should continue, ``False`` if execution
            should stop.
        """
        if logger is None:
            logger = get_logger()

        # Not simulation, execute as normal
        if self.started:
            self.reset()

        # For case that step is executed outside of XDL context.
        if not step_indexes:
            step_indexes = [0]

        # Take copy of step indexes for logging once step as finished as the
        # list will be altered by substeps
        self_step_indexes = copy.copy(step_indexes)

        self.started = True

        if self.start_block is None:
            raise XDLError('Dynamic step has not been prepared for execution.\
 if executing steps individually, please use\
 `xdl_obj.execute(platform_controller, step_index)` rather than\
 `xdl_obj.steps[step_index].execute(platform_controller)`.')

        # If platform controller simulation flag is True, run simulation steps
        if platform_controller.simulation is True:

            # Run simulation steps
            self.simulate(
                platform_controller,
                logger=logger,
                step_indexes=step_indexes,
                level=level + 1
            )

            # Log step completion and return
            logger.info(finished_executing_step_msg(self, self_step_indexes))
            return True

        # Log step start timestamp
        log_duration(self, 'start')

        substep_index = 0

        # Execute steps from on_start
        for step in self.start_block:
            step_indexes.append(0)
            step_indexes[level + 1] = substep_index
            step_indexes = step_indexes[:level + 2]
            logger.info(start_executing_step_msg(step, step_indexes))
            self.executor.execute_step(
                platform_controller,
                step,
                async_steps=self.async_steps,
                step_indexes=step_indexes,
                level=level + 1,
            )
            if isinstance(step, AbstractAsyncStep):
                self.async_steps.append(step)
            substep_index += 1

        # Repeatedly execute steps from on_continue until empty list returned
        continue_block = self.on_continue()
        self.executor.prepare_block_for_execution(self.graph, continue_block)

        while continue_block:
            for step in continue_block:
                step_indexes.append(0)
                step_indexes[level + 1] = substep_index
                step_indexes = step_indexes[:level + 2]
                logger.info(start_executing_step_msg(step, step_indexes))
                if isinstance(step, AbstractAsyncStep):
                    self.async_steps.append(step)
                self.executor.execute_step(
                    platform_controller,
                    step,
                    async_steps=self.async_steps,
                    step_indexes=step_indexes,
                    level=level + 1,
                )
                substep_index += 1

            continue_block = self.on_continue()
            self.executor.prepare_block_for_execution(
                self.graph, continue_block)

        # Execute steps from on_finish
        finish_block = self.on_finish()
        self.executor.prepare_block_for_execution(self.graph, finish_block)

        for step in finish_block:
            step_indexes.append(0)
            step_indexes[level + 1] = substep_index
            step_indexes = step_indexes[:level + 2]
            logger.info(start_executing_step_msg(step, step_indexes))
            self.executor.execute_step(
                platform_controller,
                step,
                async_steps=self.async_steps,
                step_indexes=step_indexes
            )
            if isinstance(step, AbstractAsyncStep):
                self.async_steps.append(step)
            substep_index += 1

        # Kill all threads
        self._post_finish()

        # Log step end timestamp
        log_duration(self, 'end')
        logger.info(finished_executing_step_msg(self, self_step_indexes))

        return True

    def simulate(
        self,
        platform_controller: Any,
        logger: logging.Logger = None,
        level: int = 0,
        step_indexes: List[int] = None
    ) -> str:
        """Run simulation steps to catch any errors that may occur during
        execution.

        Args:
            platform_controller (Any): Platform controller to use to run
                simulation steps. Should be in simulation mode.
            logger (logging.Logger): XDL logger object.
            level (int): Recursion level of step.
            step_indexes (List[int]): Indexes into steps list and substeps
                lists.
        """
        simulation_steps = self.get_simulation_steps()
        step_indexes.append(0)
        for i, step in enumerate(simulation_steps):
            # Don't increment level as this is done in execute method
            step_indexes[level] = i
            step_indexes = step_indexes[:level + 1]
            logger.info(
                start_executing_step_msg(step, step_indexes=step_indexes))
            self.executor.execute_step(
                platform_controller,
                step,
                async_steps=self.async_steps,
                step_indexes=step_indexes,
                level=level,
            )

    @abstractmethod
    def get_simulation_steps(self) -> List[Step]:
        """Should return all steps that it is possible for the step to run when
        it actually executes. The point of this is that due to the fact the
        steps list is not known ahead of time in a dynamic step, normal
        simulation cannot be done. So this is here to provide a means of
        specifying steps that should pass simulation.

        Returns:
            List[Step]: List of all steps that it is possible for the dynamic
            step to execute.
        """
        return []

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
        for substep in self.start_block:
            step_reagents_consumed = substep.reagents_consumed(graph)
            for reagent, volume in step_reagents_consumed.items():
                if reagent in reagents_consumed:
                    reagents_consumed[reagent] += volume
                else:
                    reagents_consumed[reagent] = volume
        return reagents_consumed

    def duration(self, graph: MultiDiGraph) -> FTNDuration:
        """Return duration of start block, since duration after that is unknown.

        Returns:
            FTNDuration: Estimated duration of step in seconds.
        """
        duration = FTNDuration(0, 0, 0)
        for step in self.start_block:
            duration += step.duration(graph)
        return duration
