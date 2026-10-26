from typing import Union, Generator, List
from .constants import (
    FILTER_TYPES,
    REACTOR_TYPES,
    ROTAVAP_TYPES,
    SEPARATOR_TYPES,
    FLASK_TYPES,
    WASTE_TYPES,
    CARTRIDGE_TYPES,
)
from ..utils.xdl_base import XDLBase

class Component(XDLBase):
    """This will be retired in future versions. Class for representing vessel in
    which reaction mixture resides.

    Args:
        id (str): ID for the component.
        component_type (str): Type of the component i.e. 'ChemputerFlask'
        chemical (str): Optional. Chemical component contains.
    """

    PROP_TYPES = {
        'id': str,
        'component_type': str,
        'chemical': str,
        'current_volume': float
    }

    DEFAULT_PROPS = {
        'chemical': None,
        'current_volume': 0.0
    }

    def __init__(
        self,
        id: str,
        component_type: str,
        chemical: str = 'default',
        current_volume: float = 'default',
        **kwargs
    ) -> None:
        super().__init__(locals())

class Hardware(object):
    """This will be retired in future versions.
    Object describing entire setup. The purpose is easily accessible lists
    of reactors, flasks, filters, wastes etc.

    Args:
        components (List[Component]): List of Component objects.
    """
    def __init__(self, components: List[Component]) -> None:

        self.components = components
        self.component_ids = [item.id for item in self.components]
        self.reactors = []
        self.flasks = []
        self.wastes = []
        self.filters = []
        self.separators = []
        self.rotavaps = []
        self.cartridges = []

        for component in self.components:
            if component.component_type in REACTOR_TYPES:
                self.reactors.append(component)

            elif component.component_type in SEPARATOR_TYPES:
                self.separators.append(component)

            elif component.component_type in FILTER_TYPES:
                self.filters.append(component)

            elif component.component_type in FLASK_TYPES:
                self.flasks.append(component)

            elif component.component_type in WASTE_TYPES:
                self.wastes.append(component)

            elif component.component_type in ROTAVAP_TYPES:
                self.rotavaps.append(component)

            elif component.component_type in CARTRIDGE_TYPES:
                self.cartridges.append(component)
        self.waste_xids = [waste.id for waste in self.wastes]

    def __getitem__(self, item: str) -> Union[Component, None]:
        """
        Get components like this: graph_hardware['filter'].
        """
        for component in self.components:
            if component.id == item:
                return component
        return None

    def __iter__(self) -> Generator[Component, None, None]:
        for item in self.components:
            yield item
