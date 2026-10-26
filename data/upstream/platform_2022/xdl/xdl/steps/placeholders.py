"""
This file exports useable step classes for every step defined in
xdl.steps.templates. The classes all return an empty list for get_steps so are
good for developing platform-independent XDL infrastructure based around the
cross-platform standard.
"""

from typing import Callable
import copy
from .templates import (
    AbstractAddStep,
    AbstractAddSolidStep,
    AbstractCleanVesselStep,
    AbstractCrystallizeStep,
    AbstractDissolveStep,
    AbstractDryStep,
    AbstractEvacuateAndRefillStep,
    AbstractEvaporateStep,
    AbstractFilterStep,
    AbstractFilterThroughStep,
    AbstractHeatChillStep,
    AbstractHeatChillToTempStep,
    AbstractIrradiateStep,
    AbstractPrecipitateStep,
    AbstractPurgeStep,
    AbstractRunColumnStep,
    AbstractSeparateStep,
    AbstractStartHeatChillStep,
    AbstractStartPurgeStep,
    AbstractStartStirStep,
    AbstractStirStep,
    AbstractStopHeatChillStep,
    AbstractStopPurgeStep,
    AbstractStopStirStep,
    AbstractTransferStep,
    AbstractWashSolidStep
)
from ..errors import XDLUnimplementedStepError

def get_init_method(template_cls: type) -> str:
    """Create executable code string to define __init__ method.

    Args:
        template_cls (type): Abstract step template class to use when making
           ``__init__`` method for placeholder class.

    Returns:
        str: Executable code string to define ``__init__`` method of placeholder
            class.
    """
    # Define method
    s = 'def __init__(self, '

    # Get args
    non_defaults = [
        prop for prop in template_cls.MANDATORY_PROP_TYPES
        if prop not in template_cls.MANDATORY_DEFAULT_PROPS
    ]

    # Get kwargs
    defaults = [
        prop for prop in template_cls.MANDATORY_PROP_TYPES
        if prop in template_cls.MANDATORY_DEFAULT_PROPS
    ]

    # Add args
    for prop in non_defaults:
        s += f'{prop}, '

    # Add kwargs
    for prop in defaults:
        s += f"{prop}='default', "

    # Add super call
    s += f'):\n    {template_cls.__name__}.__init__(self, locals())'
    return s

def placeholder_step(template_cls: type) -> Callable:
    """Decorator to generate placeholder class based on given template class.
    Placeholder class should allow the step to be used the same way as an actual
    implementation, but get_steps will always return an empty list.

    Args:
        template_cls (type): Template class such as
            :py:class:`AbstractAddStep`.

    Returns:
        Callable: Inner decorator that creates placeholder class from template
            class.
    """
    def inner_decorator(cls: type) -> type:
        """Decorator to make placeholder class using template class.

        Args:
            cls (type): Class to turn into a placeholder class.

        Returns:
            type: Placeholder class created using template class.
        """
        step_name = template_cls.MANDATORY_NAME

        # Define placeholder class
        class PlaceholderCls(template_cls):

            # Define props specification. Copies required so that globally
            # defined properties like `comment` do not interfere with the
            # `MANDATORY_PROP_TYPES` dict.
            PROP_TYPES = copy.copy(template_cls.MANDATORY_PROP_TYPES)
            DEFAULT_PROPS = copy.copy(template_cls.MANDATORY_DEFAULT_PROPS)
            PROP_LIMITS = copy.copy(template_cls.MANDATORY_PROP_LIMITS)

            # Define __init__ method
            exec(get_init_method(template_cls))

            # Define blank get_steps method
            def get_steps(self):
                return []

            def on_prepare_for_execution(self, graph):
                raise XDLUnimplementedStepError(step_name)

        # Rename class
        PlaceholderCls.__name__ = step_name

        # Return placeholder class
        return PlaceholderCls
    return inner_decorator

@placeholder_step(AbstractAddStep)
class Add:
    pass

@placeholder_step(AbstractAddSolidStep)
class AddSolid:
    pass

@placeholder_step(AbstractCleanVesselStep)
class CleanVessel:
    pass

@placeholder_step(AbstractCrystallizeStep)
class Crystallize:
    pass

@placeholder_step(AbstractDissolveStep)
class Dissolve:
    pass

@placeholder_step(AbstractDryStep)
class Dry:
    pass

@placeholder_step(AbstractEvacuateAndRefillStep)
class EvacuateAndRefill:
    pass

@placeholder_step(AbstractEvaporateStep)
class Evaporate:
    pass

@placeholder_step(AbstractFilterStep)
class Filter:
    pass

@placeholder_step(AbstractFilterThroughStep)
class FilterThrough:
    pass

@placeholder_step(AbstractHeatChillStep)
class HeatChill:
    pass

@placeholder_step(AbstractHeatChillToTempStep)
class HeatChillToTemp:
    pass

@placeholder_step(AbstractIrradiateStep)
class Irradiate:
    pass

@placeholder_step(AbstractPrecipitateStep)
class Precipitate:
    pass

@placeholder_step(AbstractPurgeStep)
class Purge:
    pass

@placeholder_step(AbstractRunColumnStep)
class RunColumn:
    pass

@placeholder_step(AbstractSeparateStep)
class Separate:
    pass

@placeholder_step(AbstractStartHeatChillStep)
class StartHeatChill:
    pass

@placeholder_step(AbstractStartPurgeStep)
class StartPurge:
    pass

@placeholder_step(AbstractStartStirStep)
class StartStir:
    pass

@placeholder_step(AbstractStirStep)
class Stir:
    pass

@placeholder_step(AbstractStopHeatChillStep)
class StopHeatChill:
    pass

@placeholder_step(AbstractStopPurgeStep)
class StopPurge:
    pass

@placeholder_step(AbstractStopStirStep)
class StopStir:
    pass

@placeholder_step(AbstractTransferStep)
class Transfer:
    pass

@placeholder_step(AbstractWashSolidStep)
class WashSolid:
    pass
