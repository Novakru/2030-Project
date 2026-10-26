import json
from typing import List, Dict, Any, Union
from xdl.metadata import Metadata

from .errors import (
    XDLJSONMissingHardwareError,
    XDLJSONMissingReagentsError,
    XDLJSONMissingStepsError,
    XDLJSONHardwareNotArrayError,
    XDLJSONReagentsNotArrayError,
    XDLJSONStepsNotArrayError,
    XDLJSONInvalidSectionError,
    XDLInvalidStepTypeError,
    XDLJSONMissingPropertiesError,
    XDLJSONMissingStepNameError,
    XDLInvalidPropError,
)
from ..platforms import AbstractPlatform
from ..reagents import Reagent
from ..steps import Step
from ..hardware import Hardware, Component
from ..utils.misc import format_property
# For type annotations
if False:
    from ..xdl import XDL

#: Valid sections for XDL JSON.
VALID_SECTIONS: List[str] = ['steps', 'reagents', 'hardware', 'metadata']

def xdl_from_json_file(
        xdl_json_file: str, platform: AbstractPlatform) -> Dict[str, Any]:
    """Convert .json file with JSON XDL format to dict containing all
    information necessary to initialise a XDL object.

    Args:
        xdl_json_file (str): Path to XDL JSON file.
        platform (AbstractPlatform): Platform to use when constructing XDL
            object.

    Returns:
        Dict[str, Any]: Dict containing all information necessary to initialise
        a XDL object. Format is the following:
        ``{ 'steps': steps, 'reagents': reagents, 'hardware': hardware }``
    """
    with open(xdl_json_file) as fd:
        xdl_json = json.load(fd)
    return xdl_from_json(xdl_json, platform)

def validate_xdl_json(xdl_json: Dict[str, Any]) -> None:
    """Validate XDL JSON Dict is correct format.

    Args:
        xdl_json (Dict[str, Any]): XDL JSON loaded into dict.

    Raises:
        XDLJSONError: Raises various subclasses of this error if the XDL JSON is
            not in the correct format.
    """
    if 'steps' not in xdl_json:
        raise XDLJSONMissingStepsError()

    if 'reagents' not in xdl_json:
        raise XDLJSONMissingReagentsError()

    if 'hardware' not in xdl_json:
        raise XDLJSONMissingHardwareError()

    if type(xdl_json['steps']) is not list:
        raise XDLJSONStepsNotArrayError()

    if type(xdl_json['reagents']) is not list:
        raise XDLJSONReagentsNotArrayError()

    if type(xdl_json['hardware']) is not list:
        raise XDLJSONHardwareNotArrayError()

    for k in xdl_json:
        if k not in VALID_SECTIONS:
            raise XDLJSONInvalidSectionError(k)

    for step_json in xdl_json['steps']:
        validate_xdl_step_json(step_json)

    for reagent_json in xdl_json['reagents']:
        validate_xdl_element_json(reagent_json)

    for component_json in xdl_json['hardware']:
        validate_xdl_element_json(component_json)

def validate_xdl_step_json(step_json: Dict[str, Any]) -> None:
    """Validate given step from XDL JSON, recursively validating any child
    steps.

    Args:
        step_json (Dict[str, Any]): Step dict from XDL JSON.

    Raises:
        XDLJSONMissingStepNameError: Step JSON is missing "name" parameter.
        XDLJSONMissingPropertiesError: Step JSON is missing "properties"
            parameter.
    """
    if 'name' not in step_json:
        raise XDLJSONMissingStepNameError()
    if 'properties' not in step_json:
        raise XDLJSONMissingPropertiesError()
    if 'children' in step_json:
        for child in step_json['children']:
            validate_xdl_step_json(child)

def validate_xdl_element_json(xdl_element_json: Dict[str, Any]) -> None:
    """Validate given xdl element from XDL JSON.

    Args:
        xdl_element_json (Dict[str, Any]): XDL element dict from XDL JSON.

    Raises:
        XDLJSONMissingPropertiesError: XDL element JSON is missing "properties"
            parameter.
    """
    if 'properties' not in xdl_element_json:
        raise XDLJSONMissingPropertiesError()

def xdl_from_json(
        xdl_json: Dict[str, Any], platform: AbstractPlatform) -> Dict[str, Any]:
    """Convert JSON XDL format dict to dict containing all data necessary for
    initialising XDL object.

    Args:
        xdl_json (Dict[str, Any]): XDL JSON loaded into dict.
        platform (AbstractPlatform): Platform to use when constructing XDL
            object.

    Returns:
        Dict[str, Any]: Dict containing all data necessary for instantiating
        XDL object. Format is the following:
        ``{ 'steps': steps, 'reagents': reagents, 'hardware': hardware }``
    """
    validate_xdl_json(xdl_json)
    xdl_steps = {
        'prep': [],
        'reaction': [],
        'workup': [],
        'purification': [],
        'no_section': []
    }
    for step_json in xdl_json['steps']:
        step = xdl_step_from_json(step_json, platform)
        # Section explicitly given, add to appropriate section
        if 'section' in step_json:
            section = step_json['section']
            xdl_steps[section].append(step)

        # Section not given, add to no section list
        else:
            xdl_steps['no_section'].append(step)

    xdl_reagents = [
        xdl_element_from_json(reagent_json, Reagent)
        for reagent_json in xdl_json['reagents']
    ]
    xdl_hardware = Hardware([
        xdl_element_from_json(reagent_json, Component)
        for reagent_json in xdl_json['hardware']
    ])
    if 'metadata' in xdl_json:
        xdl_metadata = xdl_element_from_json({
            'name': 'Metadata', 'properties': xdl_json['metadata']},
            Metadata
        )
    else:
        xdl_metadata = Metadata()
    return {
        'steps': xdl_steps,
        'reagents': xdl_reagents,
        'hardware': xdl_hardware,
        'metadata': xdl_metadata,
        'procedure_attrs': {},
    }

def xdl_step_from_json(
        step_json: Dict[str, Any], platform: AbstractPlatform) -> Step:
    """Convert JSON XDL format step Dict to Step object.

    Args:
        step_json (Dict[str, Any]): Step dict from XDL JSON to convert to Step
            object.
        platform (AbstractPlatform): Platform to use when finding step class to
            initialise.

    Raises:
        XDLInvalidPropError: Invalid prop used in ``step_json``.
        XDLInvalidStepTypeError: Invalid step type in ``step_json``.

    Returns:
        Step: Step object loaded from XDL JSON step.
    """
    step_name = step_json['name']
    if step_name not in platform.step_library:
        raise XDLInvalidStepTypeError(step_name)
    step_type = platform.step_library[step_name]
    step_properties = step_json['properties']

    # Validate properties
    for prop, val in step_properties.items():
        if prop not in step_type.PROP_TYPES and prop != 'comment':
            raise XDLInvalidPropError(step_name, prop)

        # This is necessary for sanitisation to parse value correctly
        if val == '':
            step_properties[prop] = None

    # Add children
    step_children = []
    if 'children' in step_json:
        step_children = [
            xdl_step_from_json(child, platform)
            for child in step_json['children']
        ]
    if step_children:
        step_properties['children'] = step_children

    # Instantiate step
    step = step_type(**step_properties)

    # Override step uuid with uuid given in JSON
    step.uuid = step_json['uuid']
    return step

def xdl_element_from_json(
    xdl_element_json: Dict[str, Any],
    xdl_element_type: type
) -> Union[Reagent, Component]:
    """Convert JSON XDL element dict to object of given type.

    Args:
        xdl_element_json (Dict[str, Any]): XDL element dict from XDL JSON.
        xdl_element_type (type): Reagent or Component.

    Raises:
        XDLInvalidPropError: Invalid prop given to instantiate xdl element with.

    Returns:
        Union[Reagent, Component]: Instantiated Reagent or Component object.
    """
    # Validate properties
    xdl_element_properties = xdl_element_json['properties']
    for prop, val in xdl_element_properties.items():
        if prop not in xdl_element_type.PROP_TYPES and prop != 'comment':
            raise XDLInvalidPropError(xdl_element_type.__name__, prop)
        # This is necessary for sanitisation to parse value correctly
        if val == '':
            xdl_element_properties[prop] = None
    return xdl_element_type(**xdl_element_properties)

def xdl_to_json(
        xdl_obj: 'XDL', full_properties: bool = False) -> Dict[str, Any]:
    """Convert XDL object to JSON format immediately useable by ChemIDE.

    Args:
        xdl_obj (XDL): XDL object to convert to XDL JSON.
        full_properties (bool): If True include all properties regardless of
            whether they are internal properties or the same as the default
            properties.

    Returns:
        Dict[str, Any]: XDL JSON dict produced from ``xdl_obj``.
    """
    xdl_steps_json = []
    for step in xdl_obj.steps:
        # Assign step section
        section = 'no_section'
        if step.uuid in xdl_obj.prep_steps:
            section = 'prep'
        elif step.uuid in xdl_obj.reaction_steps:
            section = 'reaction'
        elif step.uuid in xdl_obj.workup_steps:
            section = 'workup'
        elif step.uuid in xdl_obj.purification_steps:
            section = 'purification'

        # Create step JSON object and apply section
        xdl_step_json = xdl_step_to_json(step, full_properties)
        xdl_step_json['section'] = section
        xdl_steps_json.append(xdl_step_json)

    xdl_reagents_json = [
        xdl_element_to_json(reagent) for reagent in xdl_obj.reagents]
    xdl_hardware_json = [
        xdl_element_to_json(component) for component in xdl_obj.hardware]
    xdl_metadata_json = {
        k: v for k, v in xdl_obj.metadata.properties.items() if v}

    xdl_json = {
        'metadata': xdl_metadata_json,
        'steps': xdl_steps_json,
        'reagents': xdl_reagents_json,
        'hardware': xdl_hardware_json
    }
    return xdl_json

def xdl_step_to_json(
        xdl_step: Step, full_properties: bool = False) -> Dict[str, Any]:
    """Convert XDL Step to JSON format immediately useable by ChemIDE.

    Args:
        xdl_step (Step): XDL step to convert to XDL JSON format.
        full_properties (bool): If ``True`` include all properties regardless of
            whether they are internal properties or the same as the default
            properties.

    Returns:
        Dict[str, Any]: XDL JSON format dict representing ``xdl_step``.
    """
    xdl_step_properties = {
        k: format_property(
            k, v,
            xdl_step.PROP_TYPES[k],
            xdl_step.PROP_LIMITS.get(k, None),
            human_readable=False
        )
        for k, v in xdl_step.properties.items()
        if (k != 'children'
            and (full_properties or k not in xdl_step.INTERNAL_PROPS))
    }
    children = xdl_step.children if 'children' in xdl_step.properties else []
    xdl_step_json = {
        'name': xdl_step.name,
        'properties': xdl_step_properties,
        'children': [xdl_step_to_json(child) for child in children],
        'uuid': xdl_step.uuid,
    }
    return xdl_step_json

def xdl_element_to_json(xdl_step: Union[Reagent, Component]) -> Dict[str, Any]:
    """Convert XDL element to JSON format immediately useable by ChemIDE.

    Args:
        xdl_element (Union[Reagent, Component]): XDL element to convert to XDL
            JSON format.
        full_properties (bool): If ``True`` include all properties regardless of
            whether they are internal properties or the same as the default
            properties.

    Returns:
        Dict[str, Any]: XDL JSON format dict representing ``xdl_step``.
    """
    xdl_step_properties = {
        k: v for k, v in xdl_step.properties.items()
    }
    if type(xdl_step) == Reagent:
        name = xdl_step.name
    elif type(xdl_step) == Component:
        name = xdl_step.id
    xdl_step_json = {
        'name': name,
        'properties': xdl_step_properties,
    }
    return xdl_step_json
