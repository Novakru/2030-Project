"""
.. module:: graphgen.get_graph_spec
    :platforms: Unix, Windows
    :synopsis: Loads the graph specification to populate/edit the template

"""

from typing import Dict, List, Any
import copy
from ..steps import FilterThrough, Separate, Add, RunColumn

class Temp(object):
    def __init__(
        self,
        temp: float,
        active: bool,
    ):
        self.temp = temp
        self.active = active

    def __repr__(self):
        return f'Temp(temp={self.temp}, active={self.active})'

def get_graph_spec(xdl_obj, graph=None):
    graph_spec = {
        'reagents': get_flask_reagents(xdl_obj.steps),
        'buffer_flasks': get_buffer_flasks(xdl_obj, graph),
        'cartridges': get_cartridges(xdl_obj),
        'vessels': get_vessel_spec(xdl_obj),
    }

    return graph_spec

def get_flask_reagents(step_list) -> List[str]:
    """Get all flask reagents from XDL steps

    Args:
        xdl_obj (XDL): XDL object

    Returns:
        List[str]: List of all reagens from flasks
    """

    # List to store reagents
    reagents = []

    # Iterate through all XDL steps
    for step in step_list:
        # Add step with a defined volume
        if type(step) == Add and step.volume is not None:
            reagents.append(step.reagent)

        # Properties contain a solvent and solvent is defined in the step
        elif 'solvent' in step.properties and step.solvent:
            reagents.append(step.solvent)

        # Eluting solvent is in the step properties and is defined in the step
        elif 'eluting_solvent' in step.properties and step.eluting_solvent:
            reagents.append(step.eluting_solvent)

        elif 'children' in step.properties:
            reagents.extend(get_flask_reagents(step.children))

    # Sorted, unique list of all reagents
    return sorted(list(set(reagents)))

def get_buffer_flasks(xdl_obj, graph) -> List[Dict[str, Any]]:
    """Get all buffer flask related information from the XDL steps.

    Args:
        xdl_obj (XDL): XDL object

    Returns:
        List[Dict[str, Any]]: List of buffer flasks and related information.
    """

    # List to store all buffer flask info
    # Initialise with flasks declared in Hardware section
    buffer_flasks = [
        {
            'n_required': 1,
            'connected_node': None,
        }
        for component in xdl_obj.hardware
        if component.component_type == 'flask'
    ]

    # Iterate through all XDL steps
    for step in xdl_obj.steps:

        # Step is a FilterThrough and from_vessel is the same as to_vessel
        if (type(step) in [FilterThrough, RunColumn]
                and step.from_vessel == step.to_vessel):
            # Only require single flask
            buffer_flasks.append({
                'n_required': 1,
                'connected_node': step.from_vessel
            })

        # Separate step
        elif type(step) == Separate:
            # This is a nasty hack to deal with the fact that Separate
            # buffer_flasks_required is prone to changing during compilation.
            # This is because during on_prepare_for_execution, if the
            # solvent_volume is greater than the separator max volume, the
            # separation is split into multiple smaller separations. To
            # anticipate this, look at the separator max volume here to see how
            # many buffer flasks will be required.
            if graph:
                step_copy = copy.deepcopy(step)
                step_copy.split_separations_if_necessary(graph)
                n_required = step_copy.buffer_flasks_required

            else:
                n_required = step.buffer_flasks_required

            if n_required:
                buffer_flasks.append({
                    'n_required': n_required,
                    'connected_node': step.separation_vessel
                })

    # All buffer flask information
    return buffer_flasks

def get_cartridges(xdl_obj) -> List[Dict[str, Any]]:
    """Get all cartridges and related information from the XDL steps

    Args:
        xdl_obj (XDL): XDL object

    Returns:
        List[Dict[str, Any]]: Cartridges and related information
    """

    # List to hold all cartridge info
    cartridges = []
    chemicals_added = []

    # Iterate through all XDL steps
    for step in xdl_obj.steps:
        # FilterThrough step
        if type(step) == FilterThrough:
            if step.through not in chemicals_added:
                cartridges.append({
                    'from': step.from_vessel,
                    'from_type': xdl_obj.hardware[
                        step.from_vessel].component_type,
                    'to': step.to_vessel,
                    'to_type': xdl_obj.hardware[step.to_vessel].component_type,
                    'chemical': step.through
                })
                chemicals_added.append(step.through)

        # Separate step and through node is defined
        elif type(step) == Separate and step.through:
            if step.through not in chemicals_added:
                cartridges.append({
                    'from': step.separation_vessel,
                    'from_type': 'separator',
                    'to': step.to_vessel,
                    'to_type': xdl_obj.hardware[step.to_vessel].component_type,
                    'chemical': step.through,
                })
                chemicals_added.append(step.through)

    # Return cartridge info
    return cartridges

def get_vessel_spec(xdl_obj) -> Dict[str, Any]:
    """Get the vessel information from the XDL steps

    Args:
        xdl_obj (XDL): XDL object

    Returns:
        Dict[str, Any]: Vessel information
    """

    vessel_spec = {}
    component_types = []

    # Iterate through all hardware components
    for component in xdl_obj.hardware:
        # Get component ID and type if not a 'cartridge'
        if not component.component_type == 'cartridge':
            component_types.append((component.id, component.component_type))

    # Set component types and temps
    vessel_spec['temps'] = {}
    vessel_spec['types'] = component_types

    # Iterate through all XDL steps
    for step in xdl_obj.steps:
        # Iterate through the current Step's requirements
        for vessel, reqs in step.requirements.items():
            actual_vessel = step.properties[vessel]

            # Check each requirement
            for prop, val in reqs.items():
                # Temperature prop
                if prop == 'temp':
                    # Add to vessel's temp spec dict if not already defined
                    if actual_vessel not in vessel_spec['temps']:
                        vessel_spec['temps'][actual_vessel] = []

                    # Find out whether active heatchilling or not.
                    if 'active' in step.properties and step.active:
                        active = True
                    else:
                        active = False

                    vessel_spec['temps'][actual_vessel].extend([
                        Temp(temp=temp, active=active)
                        for temp in val
                    ])
    return vessel_spec
