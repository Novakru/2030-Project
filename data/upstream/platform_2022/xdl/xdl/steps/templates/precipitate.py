from typing import Dict
from .abstract_template import AbstractXDLElementTemplate
from ..base_steps import AbstractStep
from ...constants import VESSEL_PROP_TYPE, REAGENT_PROP_TYPE
from ...utils.prop_limits import (
    TEMP_PROP_LIMIT,
    TIME_PROP_LIMIT,
    ROTATION_SPEED_PROP_LIMIT,
    VOLUME_PROP_LIMIT
)
from ...utils.vessels import VesselSpec

class AbstractPrecipitateStep(AbstractXDLElementTemplate, AbstractStep):
    """Cause precipitation by optionally adding a reagent, then changing
    temperature and stirring.

    Name: Precipitate

    Mandatory props:
        vessel (vessel): Vessel to heat/chill and stir to cause precipitation.
        temp (float): Temperature to heat/chill vessel to.
        time (float): Time to stir vessel for at given temp.
        stir_speed (float): Speed in RPM at which to stir.
        reagent (str): Optional reagent to add to trigger precipitation.
        volume (float): Volume of reagent to add to trigger precipitation.
        add_time (float): Time to add reagent over.
    """
    MANDATORY_NAME = 'Precipitate'

    MANDATORY_PROP_TYPES = {
        'vessel': VESSEL_PROP_TYPE,
        'temp': float,
        'time': float,
        'stir_speed': float,
        'reagent': REAGENT_PROP_TYPE,
        'volume': float,
        'add_time': float,
    }

    MANDATORY_DEFAULT_PROPS = {
        'temp': None,
        'time': None,
        'stir_speed': None,
        'reagent': None,
        'volume': None,
        'add_time': None
    }

    MANDATORY_PROP_LIMITS = {
        'temp': TEMP_PROP_LIMIT,
        'time': TIME_PROP_LIMIT,
        'stir_speed': ROTATION_SPEED_PROP_LIMIT,
        'volume': VOLUME_PROP_LIMIT,
        'add_time': TIME_PROP_LIMIT,
    }

    @property
    def vessel_specs(self) -> Dict[str, VesselSpec]:
        return {
            'vessel': VesselSpec(
                stir=True, min_temp=self.temp, max_temp=self.temp)
        }
