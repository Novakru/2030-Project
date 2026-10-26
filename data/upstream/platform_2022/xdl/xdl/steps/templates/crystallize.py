from typing import Dict
from .abstract_template import AbstractXDLElementTemplate
from ..base_steps import AbstractStep
from ...constants import VESSEL_PROP_TYPE
from ...utils.prop_limits import (
    TEMP_PROP_LIMIT,
    TIME_PROP_LIMIT,
)
from ...utils.vessels import VesselSpec

class AbstractCrystallizeStep(AbstractXDLElementTemplate, AbstractStep):
    """Crystallize dissolved solid by ramping temperature to given temp
    over given time.

    Name: Crystallize

    Mandatory props:
        vessel (vessel): Vessel to crystallize.
        ramp_time (float): Time over which to ramp to temp.
        ramp_temp (float): Temp to ramp to over time.
    """
    MANDATORY_NAME = 'Crystallize'

    MANDATORY_PROP_TYPES = {
        'vessel': VESSEL_PROP_TYPE,
        'ramp_time': float,
        'ramp_temp': float,
    }

    MANDATORY_DEFAULT_PROPS = {
        'ramp_time': None,
        'ramp_temp': None,
    }

    MANDATORY_PROP_LIMITS = {
        'ramp_time': TIME_PROP_LIMIT,
        'ramp_temp': TEMP_PROP_LIMIT,
    }

    @property
    def vessel_specs(self) -> Dict[str, VesselSpec]:
        return {
            'vessel': VesselSpec(
                min_temp=self.ramp_temp, max_temp=self.ramp_temp)
        }
