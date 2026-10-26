# Std
from typing import List, Dict, Any, Iterator
import logging
import copy
from abc import ABC, abstractmethod

# Other
from networkx import MultiDiGraph
import termcolor

# Relative
from .step import Step
from .abstract_base_step import AbstractBaseStep
from .abstract_async_step import AbstractAwaitStep
from ..logging import start_executing_step_msg, finished_executing_step_msg
from ..utils import pretty_props_table, FTNDuration
from ...utils.logging import get_logger, log_duration


def get_base_steps(step: Step) -> List[AbstractBaseStep]:
    """Return list of given step's base steps. Recursively descends step tree
    to find base steps. Here rather than in utils as uses ``AbstractBaseStep``
    type so would cause circular import.

    Args:
        step (Step): Step to get base steps from.

    Returns:
        List[AbstractBaseStep]: List of step's base steps.
    """
    base_steps = []
    for step in step.steps:
        if isinstance(step, AbstractBaseStep):
            base_steps.append(step)
        else:
            base_steps.extend(get_base_steps(step))
    return base_steps

class AbstractStep(Step, ABC):
    """Abstract base class for all steps that contain other steps.
    Subclasses must implement steps and human_readable, and can also override
    vessel_specs if necessary.

    Attributes:
        properties (dict): Dictionary of step properties.
        human_readable (str): Description of actions taken by step.

    Args:
        param_dict (Dict[str, Any]): Step properties dict to initialize step
            with.
    """

    _steps = []
    _context = None

    def __init__(self, param_dict: Dict[str, Any]) -> None:
        super().__init__(param_dict)

        # Initialise internal steps list and properties associated with this
        # steps list.
        # self._steps = self.get_steps()
        self._update_steps()
        self._last_props = self._copy_props()

    @property
    def steps(self):
        """The internal steps list is calculated only when it is asked for, and
        only when ``self.properties`` different to the last time steps was asked
        for. This is for performance reasons since during
        ``prepare_for_execution`` the amount of updates to ``self.properties``
        is pretty large.

        ::

            # steps updated
            step = Step(**props)

            # self.properties updated but steps not updated
            step.volume = 15

            # steps updated and returned
            print(step.steps)

            # steps not updated and returned, since properties haven't change
            # since last steps update
            print(step.steps)
        """
        # Only update self._steps if self.properties has changed.
        #
        # Optimization note: This may seem long winded compared to
        # self.properties != self._last_props but in Python 3.7 at least this is
        # faster.
        should_update = False
        for k, v in self.properties.items():
            if self._last_props[k] != v:
                should_update = True
                break

        # If self.properties has changed, update self._steps
        if should_update:
            self._update_steps()
            self._last_props = self._copy_props()

        return self._steps

    def _update_steps(self):
        """Update steps with any required updates and apply ctx
        """

        self._steps = self.get_steps()
        self._add_context_to_substeps()

    def _add_context_to_substeps(self):
        """Adds CTX to all substeps of steps.
        """

        if self.context is None:
            return

        for substep in self._steps:
            substep.context = self.context

    def locks(self, platform_controller):
        """Collect all locks from underlying steps and return.
        Used by parallel XDL execution.

        Args:
            platform_controller: Platform controller.

        Returns:
            Tuple[List[str]]: All locks.
        """
        temp_locks_all, ongoing_locks_all, unlocks_all = [], [], []
        for step in self.base_steps:
            locks = step.locks(platform_controller)
            temp_locks_all += locks[0]
            ongoing_locks_all += locks[1]
            unlocks_all += locks[2]

        return (
            list(set(temp_locks_all)),
            list(set(ongoing_locks_all)),
            list(set(unlocks_all))
        )

    def _copy_props(self) -> Dict[str, Any]:
        """Return deep copy of ``self.properties`` for use when deciding whether
        to use cached :py:attr:`_steps` or not.

        Returns:
            Dict[str, Any]: Deep copy of ``self.properties`` for use when
                deciding whether to use cached :py:attr:`_steps` or not.
        """
        copy_props = {}
        for k, v in self.properties.items():
            # Don't copy callable. For example, if this is a class method,
            # copying will copy the entire object, meaning that any comparison
            # with the previous method will show them to be unequal, even if
            # the method hasn't actually changed.
            if callable(v):
                copy_props[k] = v
            else:
                copy_props[k] = copy.deepcopy(v)
        return copy_props

    @abstractmethod
    def get_steps(self) -> List[Step]:
        """Abstract method that must be overridden when creating non base steps.
        Should return a list of steps to be sequentially executed when the step
        is executed. No properties should be changed during this method. This is
        a one way street to return a list of steps based on the current
        properties of the step.

        Returns:
            List[Step]: List of steps to be sequentially executed when the step
                is executed.
        """
        return []

    def execute(
        self,
        platform_controller,
        logger: logging.Logger = None,
        level: int = 0,
        async_steps: List[str] = [],
        step_indexes: List[int] = None,
    ) -> bool:
        """
        Execute self with given platform controller object.

        Args:
            platform_controller (platform_controller): Initialised platform
                controller object.
            logger (logging.Logger): Logger to handle output step output.
            level (int): Level of recursion in step execution.
            async_steps  (List[str]): List of currently executing asynchronous
                steps. Used by any instance of ``AbstractAwaitStep`` steps
                encountered.
            step_indexes (List[int]): Indexes into steps list and substeps
                lists.

        Returns:
            bool: ``True`` if execution should continue, ``False`` if execution
            should stop.
        """
        if logger is None:
            logger = get_logger()

        # Log step start timestamp
        log_duration(self, 'start')

        # This is necessary if a step is being executed outside the context of
        # a XDL object.
        if not step_indexes:
            step_indexes = [0]
        self_step_indexes = copy.copy(step_indexes)

        # If step is at recursion level 0 logging must be done here as it won't
        # be done inside the for loop below.
        if level == 0:
            logger.info(
                start_executing_step_msg(
                    self, step_indexes=step_indexes))

        # Bump recursion level
        level += 1

        # Add a placeholder for the next index so that it can be assigned to
        # using `step_indexes[level]`
        step_indexes.append(0)

        for i, step in enumerate(self.steps):
            # Update step indexes for current sub step
            step_indexes[level] = i
            step_indexes = step_indexes[:level + 1]

            # Log step execution
            logger.info(
                start_executing_step_msg(
                    step, step_indexes=step_indexes))

            # Execute step
            try:
                # Execute all "await" steps for the corresponding
                # Asynchronous steps
                if isinstance(step, AbstractAwaitStep):
                    keep_going = step.execute(
                        async_steps,
                        logger=self.logger,
                        level=level,
                        step_indexes=step_indexes
                    )

                # Execute normal step
                else:
                    step_is_base_step = isinstance(step, AbstractBaseStep)

                    # Log base step start timestamp here, as it is easier than
                    # adding to all base step `execute` methods. Only base step
                    # logged here as normal step start / end timestamps logged
                    # at start / end of this method.
                    if step_is_base_step:
                        log_duration(step, 'start')

                    # Execute step, don't pass `step_indexes` to base step, and
                    # log step completion here. Step completion isn't needed to
                    # be logged for normal steps as it is done recursively at
                    # the end of this function.
                    if step_is_base_step:
                        # Execute step
                        keep_going = step.execute(
                            platform_controller, self.logger, level=level)

                        # Log step completion
                        logger.info(
                            finished_executing_step_msg(step, step_indexes))
                    else:
                        keep_going = step.execute(
                            platform_controller,
                            self.logger,
                            level=level,
                            step_indexes=step_indexes
                        )

                    # Log base step  end timestamp here, as it is easier than
                    # adding to all base step `execute` methods.
                    if step_is_base_step:
                        log_duration(step, 'end')

            # It is disgusting to use except Exception, but the only reason
            # here is just to provide a bit of debug information if a step
            # crashes. Might want to remove this in future.
            except Exception as e:
                step_failed_msg = termcolor.colored(
                    'Step failed', color='red', attrs=['bold'])
                step_name = termcolor.colored(
                    step.name, color='cyan', attrs=['bold'])
                props_table = termcolor.colored(
                    pretty_props_table(step.properties), color='cyan')
                logger.exception(
                    f'{step_failed_msg} {step_name}\n\
{step.human_readable()}\n{props_table}'
                )
                raise e

            # If keep_going is False break execution. This is used by the
            # Confirm step to stop execution if the user doesn't wish to
            # continue.
            if not keep_going:
                return False

        # Log step end timestamp
        log_duration(self, 'end')
        logger.info(finished_executing_step_msg(self, self_step_indexes))

        # Return `keep_going` flag as `True`.
        return True

    @property
    def base_steps(self) -> List[AbstractBaseStep]:
        """Return list of step's base steps.

        Returns:
            List[AbstractBaseStep]: Step's base steps.
        """
        base_steps = []
        for step in self.steps:
            if isinstance(step, AbstractBaseStep):
                base_steps.append(step)
            else:
                base_steps.extend(get_base_steps(step))
        return base_steps

    def duration(self, graph: MultiDiGraph) -> FTNDuration:
        """Return approximate duration in seconds of step calculated as sum of
        durations of all substeps. This method should be overridden where an
        exact or near exact duration is known. The fallback duration for base
        steps is 1 second.

        Args:
            graph (MultiDiGraph): Graph to use when calculating step duration.

        Returns:
            FTNDuration: Estimated duration of step in seconds.
        """
        duration = FTNDuration(0, 0, 0)
        for step in self.steps:
            duration += step.duration(graph)
        return duration

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
        for substep in self.steps:
            step_reagents_consumed = substep.reagents_consumed(graph)
            for reagent, volume in step_reagents_consumed.items():
                if reagent in reagents_consumed:
                    reagents_consumed[reagent] += volume
                else:
                    reagents_consumed[reagent] = volume
        return reagents_consumed

    @property
    def step_tree(self) -> Iterator[Step]:
        """Iterator yielding all substeps in step tree in depth first fashion.
        """
        for substep in self.steps:
            yield substep
            if isinstance(substep, AbstractStep):
                for subsubstep in substep.step_tree:
                    yield subsubstep

    def __getattr__(self, name: str) -> None:
        if name == "context":
            return self._context

        return super().__getattr__(name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "context":
            self._context = value
            self._add_context_to_substeps()
            return

        return super().__setattr__(name, value)
