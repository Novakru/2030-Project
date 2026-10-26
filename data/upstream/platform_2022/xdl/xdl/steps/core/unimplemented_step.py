from typing import Dict, Any
from .step import Step

class UnimplementedStep(Step):
    """Abstract base class for steps that have no implementation but are
    included either as stubs or for the purpose of showing requirements or
    ``human_readable``.

    Args:
        param_dict (Dict[str, Any]): Step properties dict to initialize step
            with.
    """
    def __init__(self, param_dict: Dict[str, Any]) -> None:
        super().__init__(param_dict)
        self.steps = []

    def execute(
            self, platform_controller, logger=None, level=0, step_indexes=None):
        raise NotImplementedError(
            f'{self.__class__.__name__} step is unimplemented.')
