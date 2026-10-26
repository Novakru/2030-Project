from typing import List

from ..base_blueprint import BaseProcedureBlueprint

from ..prep import GenericPrep
from ..reaction import GenericReaction
from ..workup import GenericWorkup
from ..purification import GenericPurification

class GenericBlueprint(BaseProcedureBlueprint):
    """Generic blueprint for entire single-reaction-step synthetic procedure.
    """

    reaction_vessel = 'reactor'
    evaporation_vessel = 'rotavap'

    PROP_TYPES = {
        'reactants': List[str],
        'solvent': str,
        'temp': float,
        'time': float,
    }

    def __init__(
        self,
        reactants: List[str],
        solvent: str,
        temp: float,
        time: float
    ):
        super().__init__(locals())

    def build_prep(self):
        return GenericPrep(
            reactants=self.reactants,
            solvent=self.solvent
        ).build()

    def build_reaction(self):
        return GenericReaction(
            temp=self.temp,
            time=self.time,
            reaction_vessel=self.reaction_vessel
        ).build()

    def build_workup(self):
        return GenericWorkup(
            reaction_vessel=self.reaction_vessel,
            evaporation_vessel=self.evaporation_vessel
        ).build()

    def build_purification(self):
        return GenericPurification().build()
