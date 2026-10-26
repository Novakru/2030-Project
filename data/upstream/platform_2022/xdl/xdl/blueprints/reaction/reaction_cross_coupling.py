from ...steps.placeholders import HeatChill
from ...utils.prop_limits import (
    TIME_PROP_LIMIT,
    TEMP_PROP_LIMIT,
)
from ..base_blueprint import BaseReactionBlueprint


class CrossCouplingReaction(BaseReactionBlueprint):
    """Template for reaction procedures.
    """

    PROP_TYPES = {
        'reaction_vessel': str,
        'temp': float,
        'time': float,
    }

    DEFAULT_PROPS = {
        'reaction_vessel': 'reactor',
        'temp': 100,
        'time': '1 hr',
    }

    PROP_LIMITS = {
        'temp': TEMP_PROP_LIMIT,
        'time': TIME_PROP_LIMIT,
    }

    def __init__(
        self,
        reaction_vessel: str = 'default',
        temp: float = 'default',
        time: float = 'default',
    ):
        super().__init__(locals())

    def build_reaction(self):
        """React for at given temp for given time."""
        reagents = []
        steps = [
            HeatChill(
                vessel=self.reaction_vessel,
                temp=self.temp,
                time=self.time,
            ),
        ]
        return steps, reagents
