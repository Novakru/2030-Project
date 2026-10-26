from typing import Any, Union, List
import hashlib
import logging
import copy
from abc import ABC
from networkx.readwrite import node_link_data
from networkx import MultiDiGraph

from .utils import do_sanity_check
from ..steps.base_steps import (
    Step,
    AbstractDynamicStep,
    AbstractBaseStep,
    AbstractAsyncStep,
    AbstractAwaitStep,
)
from ..steps.logging import (
    start_executing_step_msg, finished_executing_step_msg)
from ..steps import NON_RECURSIVE_ABSTRACT_STEPS
from ..errors import (
    XDLExecutionOnDifferentGraphError,
    XDLExecutionBeforeCompilationError
)
from ..utils.logging import get_logger, log_duration
from ..utils.graph import get_graph
if False:
    from ..xdl import XDL

class AbstractXDLExecutor(ABC):
    """Abstract class for XDL executor. The main functionality of this class is
    to perform compilation and execution of a given XDL object.

    Args:
        xdl (XDL): XDL object to compile / execute.

    Attributes:
        _prepared_for_execution (bool): Flag to specify whether self._xdl is
            ready for execution or not. Should be set to True at the end of
            :py:meth:`prepare_for_execution`.
        _xdl (XDL): XDL object passed to ``__init__``. This object will be
            altered during :py:meth:`prepare_for_execution`.
        _graph (MultiDiGraph): Graph passed to :py:meth:`prepare_for_execution`.
            ``self._xdl`` will be altered to execute on this graph during
            :py:meth`prepare_for_execution`.
        logger (logging.Logger): Logger object for executor to use when logging.
    """
    _prepared_for_execution: bool = False
    _xdl: 'XDL' = None
    _graph: MultiDiGraph = None
    logger: logging.Logger = None

    def __init__(self, xdl: 'XDL' = None) -> None:
        """Initalize ``_xdl`` and ``logger`` member variables."""
        self._xdl = xdl
        self.logger = get_logger()

    ####################
    # Abstract Methods #
    ####################

    def _graph_hash(self, graph: MultiDiGraph = None) -> str:
        """Get SHA 256 hash of graph. Used to determine whether graph used for
        execution is the same as the one used for compilation.

        Recommended to override this basic implementation, as this will give
        you a different hash if the position of nodes change, even if the
        properties and connectivity stays the same.

        Args:
            graph (MultiDiGraph): Graph to get hash of.

        Returns:
            str: Hash of graph.
        """
        if not graph:
            graph = self._graph
        return hashlib.sha256(
            str(node_link_data(graph)).encode('utf-8')
        ).hexdigest()

    def prepare_for_execution(
        self,
        graph_file: Union[str, MultiDiGraph],
        **kwargs
    ) -> None:
        """Abstract compile method. Should convert :py:attr:`_xdl` into an
        executable form.

        At the moment, the implementation of this
        method is completely open. When it becomes clear what overlap there is
        between implementation on different platforms, it could make sense to
        move some code from platform specific implementations into the abstract
        class. At the moment pretty much everything has to be done in the
        platform specific implementation.

        Tasks this method must generally complete:
            1. Map all vessels in ``self._xdl.vessel_specs`` to vessels in
               graph. This involves choosing a graph vessel to use for every
               vessel in ``self._xdl.vessel_specs``, and updating every
               occurrence of the xdl vessel in ``self._xdl.steps`` with the
               appropriate graph vessel.

            2. Add internal properties to all steps, child steps and substeps.
               This can typically be done by calling
               :py:meth:`add_internal_properties`. This may need to be done more
               than once, depending on the way in which new steps are added
               and step properties are updated during this method.

            3. Do sanity checks to make sure that the procedure is indeed
               executable. As a bare minimum :py:meth:`perform_sanity_checks`
               should be called at the end of this method.

            4. Once :py:attr:`_xdl` has been successfully prepared for
               execution, set :py:attr:`self._prepared_for_execution` to True.

        Additionally, if for any reason :py:attr:`_xdl` cannot be prepared for
        execution with the given graph, helpful, informative errors should be
        raised.

        Args:
            graph_file (Union[str, MultiDiGraph]): Path to graph file, or loaded
                graph to compile procedure with.
        """
        self._graph = get_graph(graph_file)
        self.add_internal_properties()
        self.perform_sanity_checks()
        self._prepared = True

    ########################
    # Non Abstract Methods #
    ########################

    def perform_sanity_checks(
            self, steps: List[Step] = None, graph: MultiDiGraph = None) -> None:
        """Recursively perform sanity checks on every step in steps list. If
        steps list not given defaults to ``self._xdl.steps``.

        Args:
            steps (List[Step]): List of steps to perform sanity checks
                recursively for every step / substep.
                Defaults to ``self._xdl.steps``
            graph (MultiDiGraph): Graph to use when running sanity checks. If
                not given will use :py:attr:`_graph`.
        """
        if graph is None:
            graph = self._graph
        if steps is None:
            steps = self._xdl.steps
        for step in steps:
            do_sanity_check(graph, step)

    def add_internal_properties(
        self,
        graph: MultiDiGraph = None,
        steps: List[Step] = None
    ) -> None:
        """Recursively add internal properties to all steps, child steps and
        substeps in given list of steps. If graph and steps not given use
        `self._graph` and ``self._xdl.steps``. This method recursively calls the
        ``on_prepare_for_execution`` method of every step, child step and
        substep in the step list.

        Args:
            graph (MultiDiGraph): Graph to pass to step
                ``on_prepare_for_execution`` method.
            steps (List[Step]): List of steps to add internal properties to.
                This steps in this list are altered in place, hence no return
                value.
        """
        if graph is None:
            graph = self._graph
        if steps is None:
            steps = self._xdl.steps

        # Iterate through each step
        for step in steps:
            self.add_internal_properties_to_step(graph, step)

    def add_internal_properties_to_step(
            self, graph: MultiDiGraph, step: Step) -> None:
        """Add internal properties to given step and all its substeps and
        child steps.

        Args:
            graph (MultiDiGraph): Graph to pass to step
                ``on_prepare_for_execution`` method.
            step (Step): Step to add internal properties to.
                The step is altered in place, hence no return
                value.
        """
        # Prepare the step for execution
        step.on_prepare_for_execution(graph)

        # Special case for Dynamic steps
        if isinstance(step, AbstractDynamicStep):
            step.prepare_for_execution(graph, self)

        # If the step has children, add internal properties to all children
        if 'children' in step.properties:
            self.add_internal_properties(graph, step.children)

        # Recursive steps, add internal proerties to all substeps
        if not isinstance(step, NON_RECURSIVE_ABSTRACT_STEPS):
            self.add_internal_properties(graph, step.steps)

    def prepare_dynamic_steps_for_execution(
        self,
        step: Step,
        graph: MultiDiGraph
    ) -> None:
        """Prepare any dynamic steps' start blocks for execution. This is used
        during :py:meth:`add_internal_properties` and during execution. The
        reason for using during execution is that when loaded from XDLEXE
        dynamic steps do not have a start block. In the future the start block
        of dynamic steps could potentially be saved in the XDLEXE.

        Args:
            step (Step): Step to recursively prepare any dynamic steps for
                execution.
            graph (MultiDiGraph): Graph to use when preparing for execution.
        """
        if isinstance(step, AbstractDynamicStep):
            if step.start_block is None:
                step.prepare_for_execution(graph, self)
            for substep in step.start_block:
                self.prepare_dynamic_steps_for_execution(substep, graph)
        elif not isinstance(step, NON_RECURSIVE_ABSTRACT_STEPS):
            for substep in step.steps:
                self.prepare_dynamic_steps_for_execution(substep, graph)

    def execute_step(
        self,
        platform_controller: Any,
        step: Step,
        async_steps: List[AbstractAsyncStep] = [],
        step_indexes: List[int] = None,
        level: int = 0,
    ) -> bool:
        """Execute single step.

        Args:
            platform_controller (Any): Platform controller to use to execute
                step.
            step (Step): Step to execute.
            async_steps (List[AbstractAsyncStep]): List of asynchronous steps
                to pass to step execute method if step is an a instance of
                ``AbstractAwaitStep``.

        Returns:
            bool:
                True to signify execution will continue, False to signify
                execution should stop.
        """
        # Prepare start blocks of any dynamic steps for execution.
        # This is because dynamic steps loaded from XDLEXE are not prepared
        # for execution. This needs to be changed to be compatible with other
        # platform controllers. Potentially start blocks should be saved to
        # XDLEXE.
        if hasattr(platform_controller, 'graph'):
            self.prepare_dynamic_steps_for_execution(
                step, platform_controller.graph.graph)

        try:
            # Wait for async step to finish executing
            if isinstance(step, AbstractAwaitStep):
                keep_going = step.execute(
                    async_steps,
                    logger=self.logger,
                    level=level,
                    step_indexes=step_indexes
                )

            # Execute Repeat like this so any nested Async steps get added to
            # async_steps
            elif 'Repeat' in step.name:
                # Log Repeat step start
                self.logger.info(start_executing_step_msg(
                    step, step_indexes=step_indexes))

                # Get log message for finish before step_indexes are changed
                finish_msg = finished_executing_step_msg(
                    step, step_indexes)

                if step_indexes is None:
                    step_indexes = []

                # Execute repeat children steps
                for i, substep in enumerate(step.steps):

                    # Update step indexes
                    step_indexes.append(0)
                    step_indexes = step_indexes[:level + 2]
                    step_indexes[-1] = i

                    # Log step start
                    self.logger.info(start_executing_step_msg(
                        substep, step_indexes=step_indexes))

                    # Execute step
                    keep_going = self.execute_step(
                        platform_controller,
                        substep, async_steps,
                        step_indexes=step_indexes,
                        level=level + 1
                    )

                # Log Repeat step finish
                self.logger.info(finish_msg)

            # Normal step execution
            else:
                is_base_step = isinstance(step, AbstractBaseStep)

                # Log step start timestamp
                if is_base_step:
                    log_duration(step, 'start')

                # Execute step, don't pass `step_indexes` to base steps as they
                # don't use it and don't take it as an argument in the `execute`
                # method.
                if is_base_step:
                    keep_going = step.execute(
                        platform_controller, self.logger, level=level)
                else:
                    keep_going = step.execute(
                        platform_controller,
                        self.logger,
                        # Copy of step indexes in case any funky async stuff
                        # going on
                        step_indexes=copy.copy(step_indexes),
                        level=level,
                    )

                # Log step end timestamp
                if is_base_step:
                    log_duration(step, 'end')

                # Store all asynchronous steps so that they can be awaited.
                if isinstance(step, AbstractAsyncStep):

                    # Need this check to stop Async inside Repeat adding the
                    # same step multiple times.
                    if step not in async_steps:
                        async_steps.append(step)

        # Raise any errors during step execution with additional info about step
        # that failed.
        except Exception as e:
            self.logger.info(f'Step failed {type(step)} {step.properties}')
            raise e

        return keep_going

    def execute(self, platform_controller: Any) -> None:
        """Execute XDL procedure with given platform controller.
        The same graph must be passed to the platform controller and to
        prepare_for_execution.

        Args:
            platform_controller (Any): Platform controller object to execute XDL
                with.

        Raises:
            XDLExecutionOnDifferentGraphError: If trying to execute XDLEXE on
                different graph to the one which was used to compile it.
            XDLExecutionBeforeCompilationError: Trying to execute XDL object
                before it has been compiled.
        """
        # XDLEXE, check graph hashes match
        if not self._prepared_for_execution and self._xdl.compiled:

            # Currently, this check only performed for Chemputer
            if hasattr(platform_controller, 'graph'):

                # Check graph hashes match
                if self._xdl.graph_sha256 == self._graph_hash(
                        platform_controller.graph.graph):

                    self.logger.info('Executing xdlexe, graph hashes match.')
                    self._prepared_for_execution = True

                # Graph hashes don't match raise error
                else:
                    raise XDLExecutionOnDifferentGraphError()

            # For platforms other than Chemputer just switch flag
            else:
                self._prepared_for_execution = True

        # Execute procedure
        if self._prepared_for_execution:
            self.logger.info(
                f'\nProcedure\n---------\n\n{self._xdl.human_readable()}\n\n')

            # Store all ongoing async steps, so that they can be joined later
            # if necessary.
            async_steps = []

            # Iterate through all steps and execute.
            for i, step in enumerate(self._xdl.steps):

                step.acquire_locks(platform_controller, pid='__main')

                step_indexes = [i]

                # Store all asynchronous steps so that they can be awaited.
                if isinstance(step, AbstractAsyncStep):
                    async_steps.append(step)

                # Execute step
                keep_going = self.execute_step(
                    platform_controller,
                    step,
                    async_steps=async_steps,
                    step_indexes=step_indexes
                )

                step.release_locks(platform_controller, pid='__main')

                # If return value of step execution requests execution break,
                # then return.
                if not keep_going:
                    return

        else:
            raise XDLExecutionBeforeCompilationError()
