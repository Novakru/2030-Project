import copy
from ..steps import Step
from ..hardware import Hardware
from ..xdl import XDL

def deep_copy_step(step: Step):
    """Deprecated. Step.__deepcopy__ now implemented so you can just do
    ``copy.deepcopy(step)``. This remains here for backwards compatibility
    but should eventually be removed.

    Return a deep copy of a step. Written this way with children handled
    specially for compatibility with Python 3.6.
    """
    # Copy children
    children = []
    if 'children' in step.properties and step.children:
        for child in step.children:
            children.append(deep_copy_step(child))

    # Copy properties
    copy_props = {}
    for k, v in step.properties.items():
        if k != 'children':
            copy_props[k] = v
    copy_props['children'] = children

    # Make new step
    copied_step = type(step)(**copy_props)

    return copied_step

def xdl_copy(xdl_obj: XDL) -> XDL:
    """Deprecated. XDL.__deepcopy__ now implemented so you can just do
    ``copy.deepcopy(xdl_obj)``. This remains here for backwards compatibility
    but should eventually be removed.

    Returns a deepcopy of a XDL object. copy.deepcopy can be used with
    Python 3.7, but for Python 3.6 you have to use this.

    Args:
        xdl_obj (XDL): XDL object to copy.

    Returns:
        XDL: Deep copy of xdl_obj.
    """
    copy_steps = []
    copy_reagents = []
    copy_hardware = []

    # Copy steps
    for step in xdl_obj.steps:
        copy_steps.append(deep_copy_step(step))

    # Copy reagents
    for reagent in xdl_obj.reagents:
        copy_props = copy.deepcopy(reagent.properties)
        copy_reagents.append(type(reagent)(**copy_props))

    # Copy hardware
    for component in xdl_obj.hardware:
        copy_props = copy.deepcopy(component.properties)
        copy_hardware.append(type(component)(**copy_props))

    # Return new XDL object
    return XDL(steps=copy_steps,
               reagents=copy_reagents,
               hardware=Hardware(copy_hardware),
               logging_level=xdl_obj.logging_level)
