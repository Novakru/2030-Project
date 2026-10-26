from typing import Dict, List, Tuple, Any
import itertools
import copy
import json
from networkx import MultiDiGraph

from xdl import XDL
from xdl.steps import Step, Await, Async, Wait
from xdl.hardware import Hardware

from .utils import shift_usage_times


class ScheduleStep:
    """Store info on schedule step for further use. Always kept
    within a ScheduleBlock.

    Attributes:
        start_time (int): Time in schedule when step starts.
        end_time (int): Time in schedule when step ends.
        duration (int): Total duration of step.
        node_use (Dict[str, List[int]]): Node use (adjusted by start time).
        xdl_step (Step): XDL step.
    """

    def __init__(
        self,
        xdl_step: Step,
        block_start_time: int,
        node_use: Dict[str, List[int]]
    ) -> None:
        """ScheduleStep constructor.

        Args:
            xdl_step (Step): XDL step.
            block_start_time (int): Start time of parent block.
            node_use (Dict[str, List[int]]): Node use during step.
        """
        self.xdl_step = xdl_step
        self.start_time = block_start_time

        # adjust step node use by parallelized start time
        self.node_use = shift_usage_times(node_use, block_start_time)
        self.start_time, self.end_time, self.duration = \
            self.get_step_start_end_and_duration(self.node_use)

    def get_step_start_end_and_duration(
            self, node_use: Dict[str, List[int]]) -> Tuple[int, int, int]:
        """From node use, get start, end, and duration times of
        schedule step.

        Args:
            node_use (Dict[str, List[int]]): Node use during step.

        Returns:
            [type]: [description]
        """
        flattened_times = list(itertools.chain.from_iterable(
            itertools.chain.from_iterable(
                [t for t in node_use.values()])))

        start, end = min(flattened_times), max(flattened_times)
        duration = max(flattened_times) - min(flattened_times)

        return start, end, duration

    def to_json(self):
        """Convert schedule step to JSON format.
        """
        json = {
            'name': self.xdl_step.name,
            'start_time': self.start_time,
            'end_time': self.end_time,
            'duration': self.duration,
            'node_use': self.node_use,
        }
        return json


class ScheduleBlock:
    """Storage of schedule XDL block info for further use.

    Attributes:
        start_time (int): Time in schedule when block starts.
        end_time (int): Time in schedule when block ends.
        duration (int): Total duration of block.
        node_use (Dict[str, List[int]]): Node use (adjusted by start time).
        xdl_obj (Step): XDL object.
    """

    def __init__(
        self,
        block_id: str,
        start_time: int,
        xdl_obj: XDL,
        steps: List[ScheduleStep],
        node_use: Dict[str, List[int]]
    ) -> None:
        """ScheduleBlock constructor.

        Args:
            block_id (str): Unique block name.
            start_time (int): Start time of block determined by parallelizer.
            xdl_obj (XDL): Corresponding XDL object of block.
            steps (List[ScheduleStep]): Corresponding ScheduleSteps.
            node_use (Dict[str, List[int]]): Node use times of block.
        """
        self.block_id = block_id
        self.start_time = start_time
        self.xdl_obj = xdl_obj
        self.steps = steps

        # node use times shifted by block start
        self.node_use = shift_usage_times(node_use, start_time)

        # total block duration
        self.duration = self.get_block_duration()

        # block finish time from start time & duration
        self.end_time = start_time + self.duration

    def get_block_duration(self) -> int:
        """Calculate total block duration from underlying steps.

        Returns:
            int: Block duration.
        """
        duration = 0
        for step in self.steps:
            duration += step.duration
        return duration

    def to_json(self):
        """Convert schedule block to JSON format.
        """
        json = {
            'block_id': self.block_id,
            'start_time': self.start_time,
            'end_time': self.end_time,
            'duration': self.duration,
            'node_use': self.node_use,
            'steps': []
        }

        for step in self.steps:
            json['steps'].append(step.to_json())

        return json

    def to_xdl_step(self):
        steps = []
        if self.start_time > 0:
            steps.append(Wait(self.start_time))
        steps.extend([step.xdl_step for step in self.steps])
        return Async(pid=self.block_id, children=steps)

class XDLSchedule:
    """Class to hold completed schedules, and provide easy export formats for
    execution and visualisation.

    Args:
        blocks: List[ScheduleBlock]: List of blocks produced by scheduling.
    """

    def __init__(
            self, blocks: List[ScheduleBlock], graph: MultiDiGraph) -> None:
        self.blocks = blocks
        self.makespan = max(
            self.blocks, key=lambda block: block.end_time).end_time
        self.makespan_sequential = sum(
            [block.get_block_duration() for block in self.blocks]
        )
        self.time_saved = self.makespan_sequential - self.makespan
        self.graph = graph
        self.xdl_obj = None

    def to_xdl(self):
        """Return compiled XDL object that can be used to execute procedure.
        If the object is saved as normal XDL, then it can be run after calling
        ``xdl_obj.executor.optimize_and_compile``. The full
        ``prepare_for_execution`` should not be called as the blocks in the
        schedule already have process steps added. If it does not need to be
        inspected then it can be saved directly as XDLEXE.

        Returns:
            XDL: Compiled XDL object that can be used to run schedule.
        """
        # Make XDL steps list
        xdl_steps = [block.to_xdl_step() for block in self.blocks]
        for block in self.blocks:
            xdl_steps.append(Await(pid=block.block_id))

        # Make reagents and hardware lists
        added_reagents = []
        xdl_reagents = []
        xdl_hardware = []
        for block in self.blocks:
            for reagent in block.xdl_obj.reagents:
                if reagent.name not in added_reagents:
                    xdl_reagents.append(reagent)
                    added_reagents.append(reagent.name)

            for component in block.xdl_obj.hardware:
                new_component = copy.deepcopy(component)
                # Temporary workaround so that it while product flask vessel
                # mapping is sorted out
                try:
                    new_component.id = block.xdl_obj.executor.hardware_map[
                        component.id]
                except KeyError:
                    pass
                xdl_hardware.append(new_component)

        # Make XDL object and return it
        xdl_obj = XDL(
            steps=xdl_steps,
            reagents=xdl_reagents,
            hardware=Hardware(xdl_hardware)
        )
        xdl_obj.compiled = True
        xdl_obj.graph_sha256 = self.blocks[0].xdl_obj.graph_sha256
        return xdl_obj

    def save_xdl(self, file_path: str) -> None:
        if not self.xdl_obj:
            self.xdl_obj = self.to_xdl()
        self.xdl_obj.save(file_path)

    def save_xdlexe(self, file_path: str) -> None:
        if not self.xdl_obj:
            self.xdl_obj = self.to_xdl()
        self.xdl_obj.executor.save_xdlexe(file_path)

    def to_json(self) -> Dict[str, Any]:
        """Convert schedule to JSON format that can be opened in schedule
        visualiser app.
        """
        return {
            'makespan': self.makespan,
            'nodes': list(self.graph.nodes()),
            'blocks': [block.to_json() for block in self.blocks]
        }

    def save_json(self, file_path: str) -> None:
        """Save schedule in JSON format that can be opened in schedule
        visualiser app.
        """
        with open(file_path, 'w') as fd:
            json.dump(self.to_json(), fd, indent=2)

    def __iter__(self):
        """Allow xdl schedule to be used like ``for block in xdl_schedule: ...``
        """
        return iter(self.blocks)

    def __getitem__(self, i):
        return self.blocks[i]
