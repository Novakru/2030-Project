from typing import Union, List
from ..core import AbstractStep, Step

class Repeat(AbstractStep):
    """Repeat children of this step ``self.repeats`` times.

    Args:
        repeats (int): Number of times to repeat children.
        children (List[Step]): Child steps to repeat.
    """

    PROP_TYPES = {
        'repeats': int,
        'children': Union[Step, List[Step]]
    }

    def __init__(
        self, repeats: int, children: Union[Step, List[Step]], **kwargs
    ) -> None:
        super().__init__(locals())

        if type(children) != list:
            self.children = [children]

    def get_steps(self):
        steps = []
        for _ in range(self.repeats):
            steps.extend(self.children)
        return steps

    def human_readable(self, language='en'):
        human_readable = f'Repeat {self.repeats} times:\n'
        for step in self.children:
            human_readable += f'    {step.human_readable()}\n'
        return human_readable
