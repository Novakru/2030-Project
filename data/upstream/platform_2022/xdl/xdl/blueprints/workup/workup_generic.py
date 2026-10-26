from ..base_blueprint import BaseWorkupBlueprint

class GenericWorkup(BaseWorkupBlueprint):

    PROP_TYPES = {
        'reaction_vessel': str,
        'evaporation_vessel': str,
    }

    DEFAULT_PROPS = {
        'reaction_vessel': 'reactor',
        'evaporation_vessel': 'rotavap'
    }

    def __init__(
        self,
        reaction_vessel: str = 'default',
        evaporation_vessel: str = 'default',
    ):
        super().__init__(locals())

    def build_filter(self):
        steps, reagents = [], []
        return steps, reagents

    def build_extraction(self):
        steps, reagents = [], []
        return steps, reagents

    def build_wash(self):
        steps, reagents = [], []
        return steps, reagents

    def build_dry(self):
        steps, reagents = [], []
        return steps, reagents
