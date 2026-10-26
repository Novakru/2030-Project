from .abstract_template import AbstractXDLElementTemplate
from ..base_steps import AbstractStep
from ...constants import REAGENT_PROP_TYPE
from ...utils.prop_limits import (
    VOLUME_PROP_LIMIT,
)

class AbstractResetHandlingStep(AbstractXDLElementTemplate, AbstractStep):
    """Reset all materials handling so that is fresh for the next chemical
    handling operation.

    For example, in the Chemputer after every liquid transfer, the backbone is
    cleaned with an appropriate solvent so that the next liquid to travel
    through is not contaminated.

    Name: ResetHandling

    Mandatory props:
        solvent (reagent): Solvent to use for cleaning.
        volume (float): Volume of solvent to use.
        repeats (int): Number of cleaning cycles to perform.
    """
    MANDATORY_NAME = 'ResetHandling'

    MANDATORY_PROP_TYPES = {
        'solvent': REAGENT_PROP_TYPE,
        'volume': float,
        'repeats': int,
    }

    MANDATORY_DEFAULT_PROPS = {
        'solvent': None,
        'volume': None,
        'repeats': None,
    }

    MANDATORY_PROP_LIMITS = {
        'volume': VOLUME_PROP_LIMIT,
    }
