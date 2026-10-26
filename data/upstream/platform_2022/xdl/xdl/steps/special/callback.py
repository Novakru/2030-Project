from typing import Any, Dict, Callable, List
from ..core import AbstractBaseStep

class Callback(AbstractBaseStep):
    """Call ``fn`` when this step is executed with given args.

    Args:
        AbstractBaseStep ([type]): [description]
    """
    PROP_TYPES = {
        'fn': Callable,
        'args': List[Any],
        'keyword_args': Dict[str, Any]
    }

    def __init__(
        self,
        fn: Callable,
        args: List[Any] = [],
        keyword_args: Dict[str, Any] = {}
    ) -> None:
        super().__init__(locals())

    def execute(self, chempiler, logger, level=0):
        self.fn(*self.args, **self.keyword_args)

    def locks(self, chempiler):
        return [], [], []
