from ...reagents import Reagent
from ...steps.placeholders import (
    AddSolid,
    EvacuateAndRefill,
    Evaporate,
    Filter
)

from ..base_blueprint import BaseWorkupBlueprint

class CrossCouplingWorkup(BaseWorkupBlueprint):

    PROP_TYPES = {
        'quencher': str,
        'quencher_mass': float,
        'reaction_vessel': str,
        'evaporation_vessel': str,
    }

    DEFAULT_PROPS = {
        'reaction_vessel': 'reactor',
        'evaporation_vessel': 'rotavap',
    }

    def __init__(
        self,
        quencher: str,
        quencher_mass: float,
        reaction_vessel: str = 'default',
        evaporation_vessel: str = 'default'
    ):
        super().__init__(locals())

    def build_filter(self):
        """Quench reaction, filter off quenching reagent"""
        reagents = [Reagent(self.quencher)]
        steps = [
            EvacuateAndRefill(vessel=self.reaction_vessel),
            AddSolid(
                reagent=self.quencher,
                vessel=self.reaction_vessel,
                mass=self.quencher_mass,
                stir=True,
                stir_speed="600 RPM",
            ),
            Filter(
                vessel=self.reaction_vessel,
                filtrate_vessel=self.evaporation_vessel,
            )
        ]
        return steps, reagents

    def build_dry(self):
        """Evaporate solvent"""
        reagents = []
        steps = [Evaporate(vessel=self.evaporation_vessel)]
        return steps, reagents
