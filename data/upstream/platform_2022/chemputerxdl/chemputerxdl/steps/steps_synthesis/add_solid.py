from typing import Optional, List

import copy
from networkx.classes.multidigraph import MultiDiGraph
from xdl.steps.templates import (
    AbstractAddSolidStep, AbstractAddSolidFromDispenser
)
from xdl.steps.base_steps import Step
from ..base_step import ChemputerStep
from ..steps_base.general import Confirm
from ...utils.execution import get_solid_dispenser
from ..steps_base.solid_dispenser import CDispenseSolid

class AddSolid(ChemputerStep, AbstractAddSolidStep):

    PROP_TYPES = copy.deepcopy(AbstractAddSolidStep.MANDATORY_PROP_TYPES)
    PROP_TYPES.update({
        'confirm_solid': bool,
    })
    DEFAULT_PROPS = copy.deepcopy(AbstractAddSolidStep.MANDATORY_DEFAULT_PROPS)
    DEFAULT_PROPS.update({
        'confirm_solid': True,
    })
    PROP_LIMITS = AbstractAddSolidStep.MANDATORY_PROP_LIMITS

    def __init__(
        self,
        vessel: str,
        reagent: str,
        mass: float,
        mol: float = 'default',
        time: float = 'default',
        portions: int = 'default',
        stir: bool = 'default',
        stir_speed: float = 'default',
        confirm_solid: bool = 'default',
        **kwargs
    ):
        super().__init__(locals())

    def get_steps(self):
        if self.confirm_solid:
            return [
                Confirm(f'Is {self.reagent} ({self.mass}  g) in {self.vessel}?')
            ]
        return []

class AddSolidFromDispenser(ChemputerStep, AbstractAddSolidFromDispenser):
    PROP_TYPES = AbstractAddSolidFromDispenser.MANDATORY_PROP_TYPES

    DEFAULT_PROPS = AbstractAddSolidFromDispenser.MANDATORY_DEFAULT_PROPS

    PROP_LIMITS = AbstractAddSolidFromDispenser.MANDATORY_PROP_LIMITS

    INTERNAL_PROPS = [
        'dispenser'
    ]

    def __init__(
        self,
        vessel: str,
        turns: int,
        speed: Optional[int] = 'default',
        driver: Optional[int] = 'default',
        stir: Optional[bool] = 'default',
        stir_speed: Optional[float] = 'default',

        # Internal Prop
        dispenser: Optional[str] = None,
        **kwargs
    ):
        super().__init__(locals())

    def on_prepare_for_execution(self, graph: MultiDiGraph):
        if not self.dispenser:
            self.dispenser = get_solid_dispenser(graph, self.vessel)

    def get_steps(self) -> List[Step]:
        return [
            CDispenseSolid(
                device_name=self.dispenser,
                position=self.turns,
                rpm=self.speed,
                motor_driver=self.driver
            )
        ]
