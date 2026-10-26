from typing import Dict, List, Any, Tuple
from lxml import etree
from .validation import check_attrs_are_valid
from .utils import read_file
from ..constants import SYNTHESIS_ATTRS
from ..errors import XDLError
from ..steps import Step, AbstractBaseStep
from ..reagents import Reagent
from ..hardware import Hardware, Component
from ..metadata import Metadata

# For type annotations
if False:
    from ..platforms import AbstractPlatform

def xdl_file_to_objs(
    xdl_file: str,
    platform: 'AbstractPlatform',
) -> Dict[str, Any]:
    """Given XDL file return steps, hardware and reagents.

    Args:
        xdl_file (str): Path to XDL file.
        platform (AbstractPlatform): Platform to use when constructing step
            objects from XDL file.

    Returns:
        Dict[str, Any]: All information necessary to initialise XDL object in
        form ``{ 'steps': steps, 'hardware': hardware, 'reagents': reagents }``
    """
    xdlstr = read_file(xdl_file)
    return xdl_str_to_objs(xdl_str=xdlstr, platform=platform)

def xdl_str_to_objs(
    xdl_str: str,
    platform: 'AbstractPlatform',
) -> Dict[str, Any]:
    """Given XDL str return steps, hardware and reagents.

    Args:
        xdl_str (str): XDL XML string.
        platform (AbstractPlatform): Platform to use when constructing step
            objects from XDL file.

    Returns:
        Dict[str, Any]: All information necessary to initialise XDL object in
        form ``{ 'steps': steps, 'hardware': hardware, 'reagents': reagents }``
    """
    if xdl_str:
        steps, step_record = steps_from_xdl(xdl_str, platform)
        hardware = hardware_from_xdl(xdl_str)
        reagents = reagents_from_xdl(xdl_str)
        metadata = metadata_from_xdl(xdl_str)
        synthesis_attrs = synthesis_attrs_from_xdl(xdl_str)

        # Loading xdlexe if graph_sha256 in synthesis_attrs
        if 'graph_sha256' in synthesis_attrs:
            assert len(steps['no_section']) == len(step_record)
            for i, step in enumerate(steps['no_section']):
                apply_step_record(step, step_record[i])

        parsed_xdl = {
            'steps': steps,
            'hardware': hardware,
            'reagents': reagents,
            'metadata': metadata,
        }
        parsed_xdl['procedure_attrs'] = synthesis_attrs
        return parsed_xdl
    else:
        raise XDLError('Empty XDL given.')
    return None

def apply_step_record(step: Step, step_record_step: Tuple[str, Dict]):
    assert step.name == step_record_step[0]
    for prop in step.properties:
        # Comments don't need to be applied to step record. No point adding
        # comment to substep in xdlexe.
        if prop == 'comment':
            continue

        if prop != 'children' and prop != 'uuid':
            if prop not in step_record_step[1]:
                raise XDLError(f"Property {prop} missing from\
Step {step_record_step[0]}\nThis file was most likely generated from an\
older version of XDL. Regenerate the XDLEXE file using the latest\
version of XDL.")
            step.properties[prop] = step_record_step[1][prop]
    step.update()
    if not isinstance(step, AbstractBaseStep):
        try:
            assert len(step.steps) == len(step_record_step[2])
        except AssertionError:
            raise AssertionError(f'{step.steps}\n\n{step_record_step[2]}\
 {len(step.steps)} {len(step_record_step[2])}')
        for j, substep in enumerate(step.steps):
            apply_step_record(substep, step_record_step[2][j])

def synthesis_attrs_from_xdl(xdl_str: str) -> Dict[str, Any]:
    """Return attrs from ``<Synthesis>`` tag. This used to do more but now only
    handles ``graph_sha256`` attr. If it looks like no other attrs will be used
    in the future this function could be simplified.

    Arguments:
        xdl_str (str): XDL XML string.

    Returns:
        Dict[str, Any]: Attr dict from ``<Synthesis>`` tag.
    """
    raw_attr = etree.fromstring(xdl_str).attrib
    processed_attr = {}
    for attr in SYNTHESIS_ATTRS:
        if attr['name'] in raw_attr:
            processed_attr[attr['name']] = raw_attr[attr['name']]
    return processed_attr

def metadata_from_xdl(xdl_str: str) -> Metadata:
    """Given XDL str return Metadata object.

    Arguments:
        xdl_str (str): XDL XML string.

    Returns:
        Hardware: Metadata object with any parameters included in XDL loaded
    """
    xdl_tree = etree.fromstring(xdl_str)
    for element in xdl_tree.findall('*'):
        if element.tag == 'Metadata':
            return Metadata(**element.attrib)
    return Metadata()

def steps_from_xdl(xdl_str: str, platform: 'AbstractPlatform') -> List[Step]:
    """Given XDL str return list of Step objects.

    Arguments:
        xdl_str (str): XDL XML string.
        platform (AbstractPlatform): Platform to use when constructing step
            objects from XDL file.

    Returns:
        List[Step]: List of Step objects corresponding to procedure described
        in ``xdl_str``.
    """
    steps = {
        'no_section': [],
        'prep': [],
        'reaction': [],
        'workup': [],
        'purification': [],
    }
    xdl_tree = etree.fromstring(xdl_str)
    for element in xdl_tree.findall('*'):
        if element.tag == 'Procedure':
            step_record = get_full_step_record(element)
            for child in element.findall('*'):
                if child.tag == 'Prep':
                    for step in child.findall('*'):
                        steps['prep'].append(
                            xdl_to_step(step, platform.step_library))

                elif child.tag == 'Reaction':
                    for step in child.findall('*'):
                        steps['reaction'].append(
                            xdl_to_step(step, platform.step_library))

                elif child.tag == 'Workup':
                    for step in child.findall('*'):
                        steps['workup'].append(
                            xdl_to_step(step, platform.step_library))

                elif child.tag == 'Purification':
                    for step in child.findall('*'):
                        steps['purification'].append(
                            xdl_to_step(step, platform.step_library))

                else:
                    steps['no_section'].append(
                        xdl_to_step(child, platform.step_library))
    return steps, step_record

def get_base_steps(step: etree._Element) -> List[AbstractBaseStep]:
    """Return all base steps from step XML tree, recursively.

    Args:
        step (etree._Element): Step XML tree to get base steps from.
    """
    base_steps = []
    children = step.findall('*')
    if children:
        for child in children:
            base_steps.extend(get_base_steps(child))
    else:
        return [step]
    return base_steps

def hardware_from_xdl(xdl_str: str) -> Hardware:
    """Given XDL str return Hardware object.

    Arguments:
        xdl_str (str): XDL XML string.

    Returns:
        Hardware: Hardware object containing all Component objects described
        by XDL.
    """
    return Hardware(components_from_xdl(xdl_str))

def components_from_xdl(xdl_str: str) -> List[Component]:
    """Given XDL str return list of Component objects.

    Arguments:
        xdl_str (str): XDL XML string.

    Returns:
        List[Component]: List of Component objects corresponding to
        components described in ``xdl_str``.
    """
    components = []
    xdl_tree = etree.fromstring(xdl_str)
    for element in xdl_tree.findall('*'):
        if element.tag == 'Hardware':
            for component_xdl in element.findall('*'):
                components.append(xdl_to_component(component_xdl))
    return components

def reagents_from_xdl(xdl_str: str) -> List[Reagent]:
    """Given XDL str return list of Reagent objects.

    Arguments:
        xdl_str (str): XDL XML string.

    Returns:
        List[Reagent]: List of Reagent objects corresponding to reagents
        described in ``xdl_str``.
    """
    reagents = []
    xdl_tree = etree.fromstring(xdl_str)
    for element in xdl_tree.findall('*'):
        if element.tag == 'Reagents':
            for reagent_xdl in element.findall('*'):
                reagents.append(xdl_to_reagent(reagent_xdl))
    return reagents

def xdl_to_step(
    xdl_step_element: etree._Element,
    step_type_dict: Dict[str, type]
) -> Step:
    """Given XDL step element return corresponding Step object.

    Arguments:
        xdl_step_element (etree._Element): XDL step lxml element.
        step_type_dict: Dict[str, type]: Dict of step names to step classes,
            e.g. ``{ 'Add': Add... }``


    Returns:
        Step: Step object corresponding to step in ``xdl_step_element``.
    """
    # Check if step name is valid and get step class.
    if xdl_step_element.tag not in step_type_dict:
        raise XDLError(f'{xdl_step_element.tag} is not a valid step type.')

    child_element_tags = [e.tag for e in xdl_step_element.findall('*')]
    children_steps = []
    # Nested elements like Repeat have Steps and Children elements
    # instead of just raw steps
    if 'Steps' in child_element_tags and 'Children' in child_element_tags:
        for child_element in xdl_step_element.findall('*'):
            if child_element.tag == 'Children':
                for child_step in child_element.findall('*'):
                    children_steps.append(
                        xdl_to_step(child_step, step_type_dict))
    else:
        children = xdl_step_element.findall('*')
        for child in children:
            children_steps.append(xdl_to_step(child, step_type_dict))

    step_type = step_type_dict[xdl_step_element.tag]
    # Check all attributes are valid.
    attrs = dict(xdl_step_element.attrib)
    check_attrs_are_valid(attrs, step_type)
    for attr in attrs:
        if attrs[attr].lower() == 'none':
            attrs[attr] = None

    if (not issubclass(step_type, AbstractBaseStep)
            and 'children' in step_type.__init__.__annotations__):
        attrs['children'] = children_steps

    # Try to instantiate step, any invalid values given will throw an error
    # here.
    step = step_type(**attrs)
    return step

def xdl_to_component(xdl_component_element: etree._Element) -> Component:
    """Given XDL component element return corresponding Component object.

    Arguments:
       xdl_component_element (etree._Element): XDL component lxml element.

    Returns:
        Component: Component object corresponding to component in
        ``xdl_component_element``.
    """
    attrs = dict(xdl_component_element.attrib)
    # Check 'id' is in attrs..
    if 'id' not in attrs:
        raise XDLError(
            "'id' attribute not specified for component.")
    #  Check 'type' is in attrs.
    if 'type' not in attrs:
        raise XDLError(
            f"'type' attribute not specified for {attrs['id']} component.")
    check_attrs_are_valid(attrs, Component)
    # Rename 'type' attr to 'component_type' to avoid conflict with Python
    # built-in function type.
    attrs['component_type'] = attrs['type']
    del attrs['type']
    # Try to instantiate components, any invalid values given will throw an
    # error here.
    component = Component(**attrs)
    return component

def xdl_to_reagent(xdl_reagent_element: etree._Element) -> Reagent:
    """Given XDL reagent element return corresponding Reagent object.

    Arguments:
        xdl_reagent_element (etree._Element): XDL reagent lxml element.

    Returns:
        Reagent: Reagent object corresponding to reagent in
        ``xdl_reagent_element``.
    """
    # Check attrs are valid for Reagent
    attrs = dict(xdl_reagent_element.attrib)

    # Try to instantiate Reagent object and return it.
    reagent = Reagent(**attrs)
    return reagent


##########################
# .xdlexe interpretation #
##########################

def get_full_step_record(procedure_tree: etree._Element) -> List[Tuple]:
    """Get the full step record for the procedure section of a xdlexe file.
    The step record is a nested representation of all steps and properties.
    It is needed so that top level steps can be initialised, and then properties
    of lower level steps are applied afterwards directly to the lower level
    steps. This allows editing of the xdlexe.

    Args:
        procedure_tree (etree._Element): XML tree of procedure section of XDL.

    Returns:
        List[Tuple]: Returns step record in format
        ``[(step_name, step_properties, substeps)...]``
    """
    step_record = []
    for step in procedure_tree.findall('*'):
        step_record.append(get_single_step_record(step))
    return step_record

def get_single_step_record(
        step_element: etree._Element) -> Tuple[str, Dict, List]:
    """Get step record for a single step.

    Args:
        step_element (etree._Element): XML tree for single step.

    Returns:
        Tuple[str, Dict, List]: Step record in the form
        ``(step_name, step_properties, substeps)``
    """
    children = []
    child_element_tags = [
        element.tag for element in step_element.findall('*')]
    # Nested elements like Repeat have Steps and Children elements
    # instead of just raw steps
    if 'Steps' in child_element_tags and 'Children' in child_element_tags:
        for child_element in step_element.findall('*'):
            if child_element.tag == 'Steps':
                for step in child_element.findall('*'):
                    children.append(get_single_step_record(step))
                break
    else:
        for step in step_element.findall('*'):
            children.append(get_single_step_record(step))
    return (step_element.tag, step_element.attrib, children)
