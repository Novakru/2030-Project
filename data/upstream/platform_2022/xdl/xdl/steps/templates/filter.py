from typing import Dict
from .abstract_template import AbstractXDLElementTemplate
from ..base_steps import AbstractStep
from ...constants import VESSEL_PROP_TYPE
from ...utils.prop_limits import (
    ROTATION_SPEED_PROP_LIMIT,
    TEMP_PROP_LIMIT,
    VOLUME_PROP_LIMIT
)
from ...utils.vessels import VesselSpec

class AbstractFilterStep(AbstractXDLElementTemplate, AbstractStep):
    """Filter mixture.

    Name: Filter

    Mandatory props:
        vessel (vessel): Vessel containing mixture to filter.
        filtrate_vessel (vessel): Vessel to send filtrate to. If not given,
            filtrate is sent to waste.
        stir (bool): Stir vessel while adding reagent.
        stir_speed (float): Speed in RPM at which to stir at if stir is
            ``True``.
        temp (float): Temperature to perform filtration at. Defaults to RT.
        continue_heatchill (bool): Only applies if temp is given. If ``True``
            continue temperature control after step has finished. Otherwise
            stop temperature control at end of step.
        volume (float): Volume of liquid to withdraw. If not given, volume
            should be calculated internally in the step.
    """
    MANDATORY_NAME = 'Filter'

    MANDATORY_PROP_TYPES = {
        'vessel': VESSEL_PROP_TYPE,
        'filtrate_vessel': VESSEL_PROP_TYPE,
        'stir': bool,
        'stir_speed': float,
        'temp': float,
        'volume': float,
        'continue_heatchill': bool,
    }

    MANDATORY_DEFAULT_PROPS = {
        'filtrate_vessel': None,
        'stir': True,
        'stir_speed': None,
        'temp': None,
        'volume': None,
        'continue_heatchill': False,
    }

    MANDATORY_PROP_LIMITS = {
        'stir_speed': ROTATION_SPEED_PROP_LIMIT,
        'temp': TEMP_PROP_LIMIT,
        'volume': VOLUME_PROP_LIMIT,
    }

    @property
    def vessel_specs(self) -> Dict[str, VesselSpec]:
        return {
            'vessel': VesselSpec(
                filter=True,
                stir=self.stir,
            ),
            'filtrate_vessel': VesselSpec(),
        }
