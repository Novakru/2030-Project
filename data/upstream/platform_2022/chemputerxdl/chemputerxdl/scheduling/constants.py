from typing import List

#: Node classes that do not  affect parallelisation. For example waste vessels
#: can always be moved to so don't include them in lock matrices.
IGNORE_NODE_CLASSES: List[str] = ['ChemputerWaste']

#: Code indicating that a node is not used for a given step.
NO_LOCK: int = 0

#: Code indicating that a node is used for a given step but will not remain in
#: use after the step has finished.
TEMPORARY_LOCK: int = 1

#: Code indicating that a node is used for a given step and will remain in use
#: indefinitely after the step has finished until it is explicitly unlocked.
ONGOING_LOCK: int = 2

#: Code indicating that a node is no longer in use, even if it was under an
#: ongoing lock.
UNLOCK: int = 3
