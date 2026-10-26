from typing import List, Dict

from ..constants import REAGENT_PROP_TYPE
from ..hardware import Component
from ..reagents import Reagent
from ..steps import Step
from ..errors import XDLError

def get_valid_attrs(target_class: type) -> List[str]:
    """Get valid attrs for passing to ``target_class.__init__`` methods.

    Args:
        target_class (type): Class to get valid attrs for ``__init__`` method.

    Returns:
        List[str]: List of arg names for ``target_class.__init__`` method.
    """
    valid_attrs = [
        k
        for k in target_class.PROP_TYPES
    ]
    # Add global comment property
    valid_attrs.append('comment')

    if target_class == Component:
        valid_attrs.remove('component_type')
        valid_attrs.append('type')
    return valid_attrs

def check_attrs_are_valid(attrs: Dict[str, str], target_class: type) -> None:
    """Check that attrs can be passed into ``target_class`` like
    ``target_class(**attrs)``.

    Args:
        attrs (Dict[str, str]): Attribute dict to check all keys are args of
            ``target_class.__init__`` method.
        target_class (type): ``target_class`` to check attrs are args of
            ``__init__`` method.

    Raises:
        XDLError: Error raised if any of attrs aren't args of
            ``target_class.__init__`` method.
    """
    valid_attrs = get_valid_attrs(target_class) + ['children', 'repeat']
    for attr, _ in attrs.items():
        if attr not in valid_attrs:
            raise XDLError(
                f'{attr} is not a valid attribute for {target_class.__name__}.')

def check_reagents_are_all_declared(
        steps: List[Step], reagents: List[Reagent]) -> None:
    """Check all reagents used in steps are declared in Reagents section.

    Args:
        steps (List[Step]): List of steps to check.
        reagents (List[Reagent]): List of reagents to check steps against.

    Raises:
        XDLError: Error raised if reagent used in step but not declared in
            Reagents section.
    """
    reagent_ids = [reagent.name for reagent in reagents]
    for step in steps:
        for prop, prop_type in step.PROP_TYPES.items():
            if prop_type == REAGENT_PROP_TYPE:
                step_reagent = step.properties[prop]
                if step_reagent not in reagent_ids:
                    raise XDLError(
                        f'{step_reagent} for {step.name} step not declared in\
 Reagents section.')


def check_vessels_are_all_declared(
        steps: List[Step], components: List[Component]) -> None:
    """Check all components used in steps are declared in Hardware section.

    Args:
        steps (List[Step]): List of steps to check.
        components (List[Component]): List of components to check steps against.

    Raises:
        XDLError: Error raised if component used in step but not declared in
            Hardware section.
    """
    component_ids = [component.id for component in components]
    for step in steps:
        for prop in step.properties:
            if 'vessel' in prop or prop == 'rotavap_name':
                step_vessel = step.properties[prop]
                if step_vessel and step_vessel not in component_ids:
                    raise XDLError(
                        f'{step_vessel} for {step.name} step not declared in\
 Hardware section.')
