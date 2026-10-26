from ...utils.prop_limits import (
    TIME_PROP_LIMIT,
    TEMP_PROP_LIMIT,
)
from ..base_blueprint import BaseReactionBlueprint

class GenericReaction(BaseReactionBlueprint):

    PROP_TYPES = {
        'temp': float,
        'time': float,
        'reaction_vessel': str,
    }

    PROP_LIMITS = {
        'temp': TEMP_PROP_LIMIT,
        'time': TIME_PROP_LIMIT,
    }

    def __init__(
        self,
        temp: float,
        time: float,
        reaction_vessel: str
    ):
        super().__init__(locals())

    def build_addition(self):
        steps, reagents = [], []
        return steps, reagents

    def build_reaction(self):
        steps, reagents = [], []
        return steps, reagents
