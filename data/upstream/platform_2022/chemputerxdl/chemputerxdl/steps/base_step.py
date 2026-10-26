"""
.. module:: steps.base_step
    :platforms: Unix, Windows
    :synopsis: Base representation of a Chemputer XDL step

"""
from typing import List

import time
from collections import OrderedDict
from ..localisation import HUMAN_READABLE_STEPS

from ..constants import CHEMPUTER_WASTE

class ChemputerStep:
    localisation = HUMAN_READABLE_STEPS

    @property
    def buffer_flasks_required(self):
        buffer_flasks_required = 0
        for substep in self.steps:
            buffer_flasks_required += substep.buffer_flasks_required
        return buffer_flasks_required

    def can_acquire(
        self, platform_controller, pid: str, nodes_to_lock: List[str]
    ):
        """Checks that the step can acquire all locks it needs.

        Args:
            platform_controller: Instance of Chempiler.
            pid (str): Process identifier
            nodes_to_lock (OrderedDict): Node in key and lock type as value

        Returns:
            bool: True if all nodes are lockable, else False.
        """
        for node in nodes_to_lock:
            node_lock_state = platform_controller.graph[node]['xdl_locks']
            for lock in node_lock_state.values():
                if lock.locked(pid):
                    return False

        return True

    def acquire_locks(self, platform_controller, pid: str):
        """Public method to acquire XDL locks. Used by parallelisation.

        Args:
            platform_controller: Instance of Chempiler.
            pid (str): Process identifier

        """
        temp_locks, ongoing_locks, _ = self.locks(platform_controller)

        # Avoid situation where Thread 1 & 2 both require nodes "A" & "B"
        # but Thread 1 holds node "A", Thread 2 holds "B", leading to halting
        # sorted dict helps with ongoing locks taking priority over temp locks
        nodes_to_lock = {node: "temp" for node in temp_locks}
        nodes_to_lock.update({node: "ongoing" for node in ongoing_locks})
        nodes_to_lock = OrderedDict(sorted(nodes_to_lock.items()))

        while True:
            # try to get threading lock
            if platform_controller.threading_lock.acquire(blocking=False):
                # Check if all nodes can be acquired
                if self.can_acquire(platform_controller, pid, nodes_to_lock):
                    # do the actual locking
                    self._acquire(platform_controller, pid, nodes_to_lock)
                    # release threading lock
                    platform_controller.threading_lock.release()
                    # break while loop
                    break
                else:
                    # couldn't acquire, release threading lock and wait
                    platform_controller.threading_lock.release()
                    time.sleep(1.0)
            else:
                # couldn't get threading lock, wait
                time.sleep(1.0)

    def _acquire(self, platform_controller, pid: str, nodes_to_lock: List[str]):
        """Handles locking of different lock types.

        Args:
            platform_controller: Platform controler.
            pid (str): Process acquiring locks.
            nodes_to_lock (List[str]): List of nodes to lock.

        Raises:
            Exception: Trying to access an unimplemented lock type.
        """

        for node, lock_type in nodes_to_lock.items():
            if platform_controller.graph[node]["class"] == CHEMPUTER_WASTE:
                # never lock waste vessels
                continue
            elif lock_type == "ongoing":
                self.apply_ongoing_lock(node, platform_controller, pid)
            elif lock_type == "temp":
                self.apply_temp_lock(node, platform_controller, pid)
            else:
                raise Exception(f"Invalid lock type {lock_type}.")

    def release_locks(self, platform_controller, pid: str):
        """Release XDL locks. Used by parallelisation.

        Args:
            platform_controller ([type]): [description]
            pid ([type]): [description]
        """
        temp_locks, _, unlocks = self.locks(platform_controller)

        for node in unlocks:
            node_lock_state = platform_controller.graph[node]['xdl_locks']
            ongoing_lock = node_lock_state['ongoing']
            ongoing_lock.release(pid)

        for node in temp_locks:
            node_lock_state = platform_controller.graph[node]['xdl_locks']
            node_lock_state['temp'].release(pid)

    def apply_ongoing_lock(self, node: str, platform_controller, pid: str):
        """Apply ongoing locks.

        """
        node_lock_state = platform_controller.graph[node]['xdl_locks']
        ongoing_lock = node_lock_state['ongoing']
        ongoing_lock.acquire(pid)

    def apply_temp_lock(self, node: str, platform_controller, pid: str):
        """Apply temporary locks.

        """
        node_lock_state = platform_controller.graph[node]['xdl_locks']
        ongoing_lock = node_lock_state['ongoing']

        # If no ongoing lock or ongoing lock is from same process then
        # acquire lock.
        if not ongoing_lock.locked(pid) or ongoing_lock.pid == pid:
            node_lock_state['temp'].acquire(pid)
