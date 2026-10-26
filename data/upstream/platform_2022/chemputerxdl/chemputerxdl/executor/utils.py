"""
.. module:: executor.utils
    :platforms: Windows, Unix
    :synopsis: Utilities related to execution of XDL

"""
from typing import Callable, List, Optional, Any
from networkx import MultiDiGraph

# XDL
from xdl.steps import Step

# Relative
from .constants import AQUEOUS_KEYWORDS
from ..steps import CConnect, SwitchArgon, SwitchVacuum
from ..constants import DEFAULT_PORTS

class VesselContents(object):
    """Convenience class to represents contents of one vessel.

    Attributes:
        reagents (List[str]): List of reagents flask contains.
        volume (float): Current volume of liquid in flask.
    """
    def __init__(self, reagents: List[str] = [], volume: float = 0) -> None:
        self.reagents = reagents
        self.volume = volume

    def __str__(self) -> str:
        """String representation of VesselContents

        Returns:
            str: String representation of object
        """
        return f'Reagents: {", ".join(self.reagents)}\nVolume {self.volume} mL'

    def __iter__(self) -> Optional[str]:
        """Yields the contents of the vessel

        Yields:
            Optional[str]: Reagent item
        """

        for item in self.reagents:
            yield item

def is_aqueous(reagent_name: str) -> bool:
    """Determines if a reagent is aqueous or not

    Args:
        reagent_name (str): Name of the reagent

    Returns:
        bool: Aqueous or not
    """
    # No reagent name, not aqueous
    if not reagent_name:
        return False
    else:
        # Convert name to lowercase
        reagent_name = reagent_name.lower()

        # Iterate through common aqueous names for reagents
        for keyword in AQUEOUS_KEYWORDS:
            # Keyword present in reagent name, aqeuous
            if keyword in reagent_name:
                return True

        return False

def add_default_ports_to_step(graph: MultiDiGraph, step: Step) -> Step:
    """Adds default ports to the step if ports have not been assigned.

    Args:
        step (Step): XDL Step

    Returns:
        Step: Step with default ports added
    """
    # Register changes in the step
    changed = False

    # If the step is not a Connection step
    if type(step) not in [CConnect, SwitchArgon, SwitchVacuum]:
        # Iterate through each property of the step
        for prop in step.properties:
            # Port is present but no assigned value
            if 'port' in prop and step.properties[prop] is None:
                # Replace 'port' with vessel
                vessel_prop = prop.replace('port', 'vessel')

                # Vessel is present as a property
                if vessel_prop in step.properties:
                    # Get the associated vessel name
                    vessel = step.properties[vessel_prop]
                    # Vessel is present
                    if vessel:
                        # Get the type of vessel that's present
                        vessel_class = graph.nodes[vessel]['class']
                        # Vessel type is present in the default port list
                        if vessel_class in DEFAULT_PORTS:
                            # Register the change, and assign
                            # based on value
                            changed = True
                            if 'from' in prop:
                                step.properties[prop] = DEFAULT_PORTS[
                                    vessel_class]['from']
                            else:
                                step.properties[prop] = DEFAULT_PORTS[
                                    vessel_class]['to']

    # If a change was registered, update the step
    if changed:
        step.update()

    # Return step with default ports assigned
    return step

def property_updater(step: Step, property: str) -> Callable:
    """Factory for functions to update the step property.

    Usefull to create a callback function for various "state-update" steps.

    Args:
        step (Step): A step to update the property in.
        property (float): Name of the property to update.
        new_value (Any): New value for that property.
    Returns:
        Callable: Function, that will update the property to the new value
            when called.
    """

    def update_property(new_value: Any) -> None:
        """Closure function to update the steps property to the new value."""

        step.properties[property] = new_value

    return update_property
