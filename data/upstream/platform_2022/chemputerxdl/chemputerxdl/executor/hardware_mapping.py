from typing import List, Dict
from networkx import MultiDiGraph

# XDL
from xdl.steps import Step
from xdl.hardware import Hardware, Component

# Relative
from .errors import XDLInsufficientHardwareError
from ..constants import COMPONENT_CLASS_TYPE_DICT
from ..steps import CleanBackboneDeprecated
from ..utils.execution import (
    graph_wastes,
    graph_rotavaps,
    graph_filters,
    graph_reactors,
    graph_separators
)

def check_hardware_compatibility(
    xdl_hardware: Hardware,
    graph_hardware: Hardware,
) -> bool:
    """Determine if XDL hardware object can be mapped to hardware available
    in graph.

    Returns:
        bool: Hardware is compatible or not
    """

    # Determine if there are enough hardware components for the given XDL
    enough_reactors = (len(xdl_hardware.reactors)
                       <= len(graph_hardware.reactors))
    enough_filters = (len(xdl_hardware.filters)
                      <= len(graph_hardware.filters))
    enough_separators = (len(xdl_hardware.separators)
                         <= len(graph_hardware.separators))

    # Log any hardware components where there aren't enough
    if not enough_reactors:
        raise XDLInsufficientHardwareError(
            'reactor',
            len(xdl_hardware.reactors),
            len(graph_hardware.reactors)
        )

    if not enough_filters:
        raise XDLInsufficientHardwareError(
            'filter',
            len(xdl_hardware.filters),
            len(graph_hardware.filters)
        )

    if not enough_separators:
        raise XDLInsufficientHardwareError(
            'separator',
            len(xdl_hardware.separators),
            len(graph_hardware.separators)
        )

###############################
# MAP GRAPH HARDWARE TO STEPS #
###############################

def get_hardware_map(
    xdl_hardware: Hardware,
    graph: MultiDiGraph,
) -> None:
    """
    Get map of hardware IDs in XDL to hardware IDs in graphML.
    """

    # Create empty dictionary to hold the hardware
    xdl_hardware_map = {}

    # Iterate through the XDL hardware and Graph hardware to create the map
    for xdl_hardware_list, graph_hardware_list in zip(
        [xdl_hardware.reactors, xdl_hardware.filters,
            xdl_hardware.separators, xdl_hardware.rotavaps],
        [list(graph_reactors(graph)), list(graph_filters(graph)),
            list(graph_separators(graph)), list(graph_rotavaps(graph))]
    ):

        # sort XDL and Graph hardware by id
        xdl_hardware_list = sorted(
            xdl_hardware_list, key=lambda x: x.id
        )
        graph_hardware_list = sorted(
            graph_hardware_list
        )

        # Map the Graph hardware IDs to the XDL hardware IDs
        for i in range(len(xdl_hardware_list)):
            xdl_hardware_map[
                xdl_hardware_list[i].id
            ] = graph_hardware_list[i]
            for j, item in enumerate(xdl_hardware.components):
                if item.id == xdl_hardware_list[i].id:
                    xdl_hardware.components.pop(j)
                    break
            xdl_hardware.components.append(
                Component(
                    id=graph_hardware_list[i],
                    component_type=COMPONENT_CLASS_TYPE_DICT[
                        graph.nodes[graph_hardware_list[i]]['class']]
                )
            )

    return xdl_hardware_map

def map_hardware_to_step_list(
        step_list: List[Step], hardware_map: Dict[str, str]) -> None:
    """Associate hardware to each XDL step

    Args:
        step_list (List[Step]): List of XDL steps.
    """

    # Iterate through each step to map hardware
    for step in step_list:
        # Change all vessel IDs in steps to corresponding ones in graph.
        for prop, val in step.properties.items():
            # Update the step properties if present in the XDL hardware map
            if type(val) == str and val in hardware_map:
                step.properties[prop] = hardware_map[val]

        # Update the step
        step.update()

        if hasattr(step, 'children') and step.children:
            map_hardware_to_step_list(step.children, hardware_map)

def map_hardware_to_steps(
    graph: MultiDiGraph,
    steps: List[Step],
    hardware_map: Dict[str, str]
) -> None:
    """
    Go through steps in XDL and replace XDL hardware IDs with IDs
    from the graph.
    """
    map_hardware_to_step_list(steps, hardware_map)

    # Give IDs of all waste vessels to clean backbone steps.
    for step in steps:
        if type(step) == CleanBackboneDeprecated and not step.waste_vessels:
            step.waste_vessels = list(graph_wastes(graph))
