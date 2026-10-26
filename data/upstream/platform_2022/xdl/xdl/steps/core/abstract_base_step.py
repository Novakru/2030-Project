# Std
from typing import Dict, Any
from abc import ABC, abstractmethod

# Relative
from .step import Step


class AbstractBaseStep(Step, ABC):
    """Abstract base class for all steps that do not contain other steps and
    instead have an execute method that takes a ``platform_controller`` object.

    Subclasses must implement execute.

    Args:
        param_dict (Dict[str, Any]): Step properties dict to initialize step
            with.
    """

    def __init__(self, param_dict: Dict[str, Any]) -> None:
        super().__init__(param_dict)
        self.steps = []

    @abstractmethod
    def execute(self, platform_controller) -> bool:
        """Execute method to be overridden for all base steps. Take platform
        controller and use it to execute the step. Return ``True`` if procedure
        should continue after the step is completed, return ``False`` if the
        procedure should break for some reason.
        """
        return False

    @property
    def base_steps(self):
        """Just return self as the base_steps. Used by recursive ``base_steps``
        method of ``AbstractStep``. No need to override this.
        """
        return [self]
