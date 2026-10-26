from .errors import ChempilerError

class ChempilerXDLLockReleaseError(ChempilerError):
    def __init__(self, node, locked_pid, released_pid):
        self.node = node
        self.locked_pid = locked_pid
        self.released_pid = released_pid

    def __str__(self):
        return (
            f'Node {self.node} trying to release lock with PID {self.released_pid},\
when lock was acquired with PID {self.locked_pid}.'
        )

class XDLLock:
    """The following class holds the current lock state for a given
    graph node required by multi-threaded XDL.
    """

    #: Interval in seconds to wait between attempts at acquiring lock
    # wait_interval = 0.5

    def __init__(self, node):
        self.node = node
        self.pid = None

    def acquire(self, pid):
        """Acquire lock with given pid."""
        if self.pid == pid:
            return
        self.pid = pid

    def release(self, pid):
        """Release lock with given pid. Raise error if current lock doesn't
        match given pid.
        """
        # lock is already released
        if self.pid is None:
            return
        # release lock
        elif self.pid == pid:
            self.pid = None
        else:
            raise ChempilerXDLLockReleaseError(
                node=self.node,
                locked_pid=self.pid,
                released_pid=pid,
            )

    def locked(self, pid):
        """Check if locked.

        Args:
            pid (str): Process ID.

        Returns:
            bool: True if locked, False otherwise.
        """
        # not locked, can be locked
        if self.pid is None:
            return False
        # locked by same pid, can be locked
        elif self.pid == pid:
            return False
        # not locked
        else:
            return True
