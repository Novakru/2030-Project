from typing import Dict
from .abstract_template import AbstractXDLElementTemplate
from ..base_steps import AbstractStep
from ...utils.prop_limits import VOLUME_PROP_LIMIT, TEMP_PROP_LIMIT
from ...utils.vessels import VesselSpec
from ...constants import VESSEL_PROP_TYPE, REAGENT_PROP_TYPE

class AbstractCleanVesselStep(AbstractXDLElementTemplate, AbstractStep):
    """Clean vessel.

    Name: CleanVessel

    Mandatory props:
        vessel (vessel): Vessel to clean.
        solvent (reagent): Solvent to clean vessel with.
        volume (float): Volume of solvent to clean vessel with.
        temp (float): Temperature to heat vessel to while cleaning.
        repeats (int): Number of cleaning cycles to perform.
    """
    MANDATORY_NAME = 'CleanVessel'

    MANDATORY_PROP_TYPES = {
        'vessel': VESSEL_PROP_TYPE,
        'solvent': REAGENT_PROP_TYPE,
        'volume': float,
        'temp': float,
        'repeats': int,
    }

    MANDATORY_DEFAULT_PROPS = {
        'volume': None,
        'temp': None,
        'repeats': None,
    }

    MANDATORY_PROP_LIMITS = {
        'volume': VOLUME_PROP_LIMIT,
        'temp': TEMP_PROP_LIMIT,
    }

    @property
    def vessel_specs(self) -> Dict[str, VesselSpec]:
        return {
            'vessel': VesselSpec(
                stir=True,
                min_temp=self.temp,
                max_temp=self.temp,
            )
        }
