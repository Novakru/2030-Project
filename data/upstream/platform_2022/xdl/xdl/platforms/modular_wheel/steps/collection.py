from typing import Dict

from . import stirrer
from . import base_steps
from . import add
from ....steps import special_steps
import copy
import inspect

#: Dictionary of base step name keys and step class values.
BASE_STEP_OBJ_DICT: Dict[str, type] = {
    m[0]: m[1] for m in inspect.getmembers(base_steps, inspect.isclass)}

#: Dictionary of utility step name keys and step class values.
ADD_STEP_OBJ_DICT: Dict[str, type] = {
    m[0]: m[1] for m in inspect.getmembers(add, inspect.isclass)}

#: Dictionary of synthesis step name keys and step class values.
STIRRER_STEP_OBJ_DICT: Dict[str, type] = {
    m[0]: m[1] for m in inspect.getmembers(stirrer, inspect.isclass)}

#: Dictionary of special step name keys and step class values.
SPECIAL_STEP_OBJ_DICT: Dict[str, type] = {
    m[0]: m[1] for m in inspect.getmembers(special_steps, inspect.isclass)}

#: Dictionary of all step name keys and step class values.
STEP_OBJ_DICT: Dict[str, type] = copy.copy(BASE_STEP_OBJ_DICT)
STEP_OBJ_DICT.update(ADD_STEP_OBJ_DICT)
STEP_OBJ_DICT.update(STIRRER_STEP_OBJ_DICT)
STEP_OBJ_DICT.update(SPECIAL_STEP_OBJ_DICT)
