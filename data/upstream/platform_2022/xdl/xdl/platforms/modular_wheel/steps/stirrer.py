from typing import List
from .base_steps import CBSetStirRate, CBWait
from ....steps.base_steps import Step, AbstractStep

class StartStir(AbstractStep):
    def __init__(
        self,
        stir_speed: int,
        **kwargs
    ):
        super().__init__(locals())

    def get_steps(self) -> List[Step]:
        return [
            CBSetStirRate(self.stir_speed)
        ]

class StopStir(AbstractStep):
    def __init__(
        self,
        **kwargs
    ):
        super().__init__(locals())

    def get_steps(self) -> List[Step]:
        return [
            CBSetStirRate(0)
        ]

class Stir(AbstractStep):
    def __init__(
        self,
        stir_speed: int,
        time: int,
        **kwargs
    ) -> None:
        super().__init__(locals())

    def get_steps(self) -> List[Step]:
        return [
            StartStir(self.stir_speed),
            CBWait(self.time),
            StopStir()
        ]
