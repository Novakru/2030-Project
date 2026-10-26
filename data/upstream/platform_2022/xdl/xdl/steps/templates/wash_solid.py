from typing import Union, Dict
from .abstract_template import AbstractXDLElementTemplate
from ..base_steps import AbstractStep
from ...constants import VESSEL_PROP_TYPE, REAGENT_PROP_TYPE
from ...utils.prop_limits import (
    TEMP_PROP_LIMIT,
    TIME_PROP_LIMIT,
    ROTATION_SPEED_PROP_LIMIT,
    WASH_SOLID_STIR_PROP_LIMIT
)
from ...utils.vessels import VesselSpec

class AbstractWashSolidStep(AbstractXDLElementTemplate, AbstractStep):
    """Wash solid with by adding solvent and filtering.

    Name: WashSolid

    Mandatory props:
        vessel (vessel): Vessel containing solid to wash.
        solvent (reagent): Solvent to wash solid with.
        volume (float): Volume of solvent to use.
        filtrate_vessel (vessel): Vessel to send filtrate to. If ``None``,
            filtrate is sent to waste.
        temp (float): Temperature to apply to vessel during washing.
        stir (Union[bool, str]): If ``True``, start stirring before solvent is
            added and stop stirring after solvent is removed. If ``'solvent'``,
            start stirring after solvent is added and stop stirring before
            solvent is removed. If ``False``, do not stir at all.
        stir_speed (float): Speed at which to stir at.
        time (float): Time to wait for between adding solvent and removing
            solvent.
        repeats (int): Number of washes to perform.
    """
    MANDATORY_NAME = 'WashSolid'

    MANDATORY_PROP_TYPES = {
        'vessel': VESSEL_PROP_TYPE,
        'solvent': REAGENT_PROP_TYPE,
        'volume': float,
        'filtrate_vessel': VESSEL_PROP_TYPE,
        'temp': float,
        'stir': Union[str, bool],
        'stir_speed': float,
        'time': float,
        'repeats': int,
    }

    MANDATORY_DEFAULT_PROPS = {
        'filtrate_vessel': None,
        'temp': None,
        'stir': True,
        'stir_speed': None,
        'time': None,
        'repeats': 1,
    }

    MANDATORY_PROP_LIMITS = {
        'temp': TEMP_PROP_LIMIT,
        'stir': WASH_SOLID_STIR_PROP_LIMIT,
        'stir_speed': ROTATION_SPEED_PROP_LIMIT,
        'time': TIME_PROP_LIMIT,
    }

    @property
    def vessel_specs(self) -> Dict[str, VesselSpec]:
        return {
            'vessel': VesselSpec(
                filter=True,
                stir=self.stir is not False,
                min_temp=self.temp,
                max_temp=self.temp,
            ),
            'filtrate_vessel': VesselSpec(),
        }
