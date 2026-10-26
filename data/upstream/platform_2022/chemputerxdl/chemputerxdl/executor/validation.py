from typing import List, Union
from networkx import MultiDiGraph

# XDL
from xdl.steps import Step, NON_RECURSIVE_ABSTRACT_STEPS

# Relative
from .errors import XDLNotEnoughBufferFlasksError, XDLInvalidPortError
from ..constants import VALID_PORTS
from ..utils.execution import get_buffer_flask
from ..steps import Separate, RunColumn, FilterThrough

###################
# Port Validation #
###################

def validate_ports(graph: MultiDiGraph, steps: List[Step] = None):
    """Validates the ports in each step of the XDL

    Args:
        steps (List[Step], optional): List of XDL steps. Defaults to None.
    """
    # Iterate through each XDL step
    for step in steps:
        # Validate the ports in each step
        validate_ports_step(graph, step)

def validate_ports_step(graph, step: Step):
    """Validates the ports on a XDL step.
    Ports being the Chemputer ports used for transfer of material.

    Args:
        step (Step): XDL Step to validate ports for
    """

    # Iterate through list of vessel names and valid ports for the vessel
    for vessel_keyword, port_keyword in [
        ('from_vessel', 'from_port'),
        ('to_vessel', 'to_port'),
        ('vessel', 'port'),
    ]:
        # Vessel type is in the step properties
        if vessel_keyword in step.properties:
            # Port type is present in the step properties
            if port_keyword in step.properties:
                # If the port is not null, validate the port
                if step.properties[port_keyword] is not None:
                    validate_port(
                        step.properties[vessel_keyword],
                        graph.nodes[
                            step.properties[vessel_keyword]]['class'],
                        step.properties[port_keyword]
                    )

    # If the step is not a Non-Recursive step, validate the steps of
    # each substep in this current step
    if not isinstance(step, NON_RECURSIVE_ABSTRACT_STEPS):
        for substep in step.steps:
            validate_ports_step(graph, substep)

def validate_port(vessel: str, vessel_class: str, port: Union[str, int]):
    """Validates the ports for a given vessel.
    Checks that ports supplied match those of the vessel's class type

    Args:
        vessel (str): Name of the vessel
        vessel_class (str): Type of vessel
        port (Union[str, int]): Ports supplied for the given vessel

    Raises:
        XDLInvalidPortError: Ports are invalid for vessel type
    """

    # Check the ports are valid for the given vessel
    try:
        assert str(port) in VALID_PORTS[vessel_class]

    # Ports are not valid, raise error
    except AssertionError:
        raise XDLInvalidPortError(vessel, vessel_class, port)

#########
# Other #
#########

def check_enough_buffer_flasks(graph, steps: List[Step]) -> None:
    """Checks if there are enough buffer flasks present for required steps.
    Required steps being:
        Separate
        RunColumn
        FilterThrough

    Raises:
        XDLNotEnoughBufferFlasksError: If buffer flasks required is greater
            than buffer flasks present in the graph.
    """

    # Empty lists to store flask information
    buffer_flasks_required = []
    buffer_flasks_present = []
    vessels_for_search = []

    # Iterate through each XDL step.
    # Look for steps that require buffer flasks.
    for step in steps:
        # Separate step
        if type(step) == Separate:
            # Add any required buffer flasks if present.
            # If present, add separation vessel to search list
            buffer_flasks_required.append(step.buffer_flasks_required)
            if step.buffer_flasks_required:
                vessels_for_search.append(step.separation_vessel)

        # RunColumn and FilterThrough steps
        elif type(step) in [RunColumn, FilterThrough]:
            # Add any required buffer flasks if present.
            # If present, add source vessel (from_vessel) to search list
            buffer_flasks_required.append(step.buffer_flasks_required)
            if step.buffer_flasks_required:
                vessels_for_search.append(step.from_vessel)

    # Buffer flasks are required
    if buffer_flasks_required:
        # Get the maximum number of flasks required
        buffer_flasks_required = max(buffer_flasks_required)

        # Iterate through the unique vessels in the search list
        for vessel in list(set(vessels_for_search)):
            # Get each unique vessel from the Chemputer graph if present
            vessel_buffer_flasks = get_buffer_flask(
                graph, vessel, return_single=False)

            # If vessels are present, add to buffer flask list
            if vessel_buffer_flasks:
                buffer_flasks_present.extend(vessel_buffer_flasks)

        # Get the total number of buffer flasks present
        buffer_flasks_present = len(buffer_flasks_present)

        if buffer_flasks_present < buffer_flasks_required:
            raise XDLNotEnoughBufferFlasksError(
                buffer_flasks_required, buffer_flasks_present
            )

    return True
