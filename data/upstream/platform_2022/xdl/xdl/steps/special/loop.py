from typing import Union, List
from ..core import AbstractDynamicStep, Step

class Loop(AbstractDynamicStep):
    """Repeat children of this step indefinitely.

    Args:
        children (List[Step]): Child steps to repeat.

    """

    PROP_TYPES = {
        'children': Union[Step, List[Step]]
    }

    def __init__(
        self, children: Union[Step, List[Step]], **kwargs
    ) -> None:
        super().__init__(locals())

        if type(children) != list:
            self.children = [children]

    def on_start(self):
        """Nothing to be done."""
        return []

    def on_continue(self):
        """Perform child steps"""
        return self.children

    def on_finish(self):
        """Nothing to be done."""
        return []
