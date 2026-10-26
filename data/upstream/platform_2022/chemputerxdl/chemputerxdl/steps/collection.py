"""
.. module:: steps.collection
    :platforms: Unix, Windows
    :synopsis: Collection of step names and values associated to each step

"""

from typing import Dict
from . import steps_synthesis
from . import steps_utility
from . import steps_base
from . import unimplemented_steps
from xdl.steps import special_steps
import copy
import inspect

#: Dictionary of base step name keys and step class values.
BASE_STEP_OBJ_DICT: Dict[str, type] = {
    m[0]: m[1] for m in inspect.getmembers(steps_base, inspect.isclass)
}

#: Dictionary of utility step name keys and step class values.
UTILITY_STEP_OBJ_DICT: Dict[str, type] = {
    m[0]: m[1] for m in inspect.getmembers(steps_utility, inspect.isclass)
}

#: Dictionary of synthesis step name keys and step class values.
SYNTHESIS_STEP_OBJ_DICT: Dict[str, type] = {
    m[0]: m[1] for m in inspect.getmembers(steps_synthesis, inspect.isclass)
}

#: Dictionary of special step name keys and step class values.
SPECIAL_STEP_OBJ_DICT: Dict[str, type] = {
    m[0]: m[1] for m in inspect.getmembers(special_steps, inspect.isclass)
}

#: Dictionary of unimplemented step name keys and step class values.
UNIMPLEMENTED_STEP_OBJ_DICT: Dict[str, type] = {
    m[0]: m[1]
    for m in inspect.getmembers(unimplemented_steps, inspect.isclass)
}

#: Dictionary of all step name keys and step class values.
STEP_OBJ_DICT: Dict[str, type] = copy.copy(BASE_STEP_OBJ_DICT)
STEP_OBJ_DICT.update(SPECIAL_STEP_OBJ_DICT)
STEP_OBJ_DICT.update(UTILITY_STEP_OBJ_DICT)
STEP_OBJ_DICT.update(SYNTHESIS_STEP_OBJ_DICT)
STEP_OBJ_DICT.update(UNIMPLEMENTED_STEP_OBJ_DICT)
