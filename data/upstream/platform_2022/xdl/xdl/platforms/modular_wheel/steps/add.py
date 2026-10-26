from typing import List
from ....steps.base_steps import Step, AbstractStep
from .base_steps import CBDispense, CBTurnWheel

class Add(AbstractStep):
    def __init__(
        self,
        reagent: str,
        volume: float,
        vessel: str,
        in_valve: str = "I",
        out_valve: str = "O",
        n_turns: int = 0,
        children: List = [],
    ) -> None:
        super().__init__(locals())

    def get_steps(self) -> List[Step]:
        steps = []
        steps.append(CBTurnWheel(self.n_turns))

        steps.append(CBDispense(self.reagent,
                                self.volume,
                                in_valve=self.in_valve,
                                out_valve=self.out_valve))

        return steps
