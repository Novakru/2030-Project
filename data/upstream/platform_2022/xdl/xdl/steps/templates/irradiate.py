from typing import Dict
from .abstract_template import AbstractXDLElementTemplate
from ..base_steps import AbstractStep
from ...constants import VESSEL_PROP_TYPE
from ...utils.prop_limits import (
    TEMP_PROP_LIMIT,
    TIME_PROP_LIMIT,
    ROTATION_SPEED_PROP_LIMIT,
    WAVELENGTH_PROP_LIMIT,
)
from ...utils.vessels import VesselSpec

class AbstractIrradiateStep(AbstractXDLElementTemplate, AbstractStep):
    """Irradiate reaction mixture with light of given wavelength.

    Name: Irradiate

    Mandatory props:
        vessel (vessel): Vessel to irradiate.
        wavelength (float): Wavelength of light to irradiate vessel with.
        time (float): Time to stir vessel for at given temp.
        temp (float): Temperature to heat/chill vessel to.
        stir (bool): If ``True`` then stir vessel.
        stir_speed (float): Speed in RPM at which to stir.
    """
    MANDATORY_NAME = 'Irradiate'

    MANDATORY_PROP_TYPES = {
        'vessel': VESSEL_PROP_TYPE,
        'wavelength': float,
        'time': float,
        'temp': float,
        'stir': bool,
        'stir_speed': float,
    }

    MANDATORY_DEFAULT_PROPS = {
        'temp': None,
        'stir': True,
        'stir_speed': None,
    }

    MANDATORY_PROP_LIMITS = {
        'temp': TEMP_PROP_LIMIT,
        'time': TIME_PROP_LIMIT,
        'stir_speed': ROTATION_SPEED_PROP_LIMIT,
        'wavelength': WAVELENGTH_PROP_LIMIT
    }

    @property
    def vessel_specs(self) -> Dict[str, VesselSpec]:
        return {
            'vessel': VesselSpec(
                irradiate=True,
                stir=self.stir,
                min_temp=self.temp,
                max_temp=self.temp,
            ),
        }
