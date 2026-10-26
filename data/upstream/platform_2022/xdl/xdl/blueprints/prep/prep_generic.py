from typing import List
from ..base_blueprint import BasePrepBlueprint

class GenericPrep(BasePrepBlueprint):

    PROP_TYPES = {
        'reactants': List[str],
        'solvent': str,
    }

    def __init__(
        self,
        reactants: List[str],
        solvent: str
    ):
        super().__init__(locals())

    def build_prep(self):
        steps, reagents = [], []
        return steps, reagents
