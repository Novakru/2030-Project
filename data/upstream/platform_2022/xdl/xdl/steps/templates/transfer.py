from typing import Dict
from .abstract_template import AbstractXDLElementTemplate
from ..base_steps import AbstractStep
from ...constants import VESSEL_PROP_TYPE, REAGENT_PROP_TYPE
from ...utils.prop_limits import VOLUME_PROP_LIMIT, TIME_PROP_LIMIT
from ...utils.vessels import VesselSpec

class AbstractTransferStep(AbstractXDLElementTemplate, AbstractStep):
    """Transfer liquid from one vessel to another.

    Name: Transfer

    Mandatory props:
        from_vessel (vessel): Vessel to transfer liquid from.
        to_vessel (vessel): Vessel to transfer liquid to.
        volume (float): Volume of liquid to transfer from from_vessel to
            to_vessel.
        time (float): Time over which to transfer liquid.
        viscous (bool): If ``True``, adapt process to handle viscous liquid,
            e.g. use slower move speed.
        rinsing_solvent (reagent): Solvent to rinse from_vessel with, and
            transfer rinsings to ``to_vessel``.
        rinsing_volume (float): Volume of ``rinsing_solvent`` to rinse
            ``from_vessel`` with.
        rinsing_repeats (int): Number of rinses to perform.
    """
    MANDATORY_NAME = 'Transfer'

    MANDATORY_PROP_TYPES = {
        'from_vessel': VESSEL_PROP_TYPE,
        'to_vessel': VESSEL_PROP_TYPE,
        'volume': float,
        'time': float,
        'viscous': bool,
        'rinsing_solvent': REAGENT_PROP_TYPE,
        'rinsing_volume': float,
        'rinsing_repeats': int,
    }

    MANDATORY_DEFAULT_PROPS = {
        'viscous': False,
        'time': None,
        'rinsing_solvent': None,
        'rinsing_volume': None,
        'rinsing_repeats': None,
    }

    MANDATORY_PROP_LIMITS = {
        'volume': VOLUME_PROP_LIMIT,
        'time': TIME_PROP_LIMIT,
        'rinsing_volume': VOLUME_PROP_LIMIT,
    }

    @property
    def vessel_specs(self) -> Dict[str, VesselSpec]:
        return {
            'from_vessel': VesselSpec(),
            'to_vessel': VesselSpec(),
        }
