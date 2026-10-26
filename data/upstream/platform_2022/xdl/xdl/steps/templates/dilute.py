from typing import Dict
from .abstract_template import AbstractXDLElementTemplate
from ..base_steps import AbstractStep
from ...constants import VESSEL_PROP_TYPE, REAGENT_PROP_TYPE
from ...utils.prop_limits import (
    VOLUME_PROP_LIMIT,
    ROTATION_SPEED_PROP_LIMIT,
    TIME_PROP_LIMIT
)
from ...utils.vessels import VesselSpec

class AbstractDiluteStep(AbstractXDLElementTemplate, AbstractStep):
    """Dilute reagein in vessel to volume with solvent.

    Name: Dilute

    Mandatory props:
    vessel (vessel): Vessel to be diluted in.
    reagent (reagent): Solvent to dilute with.
    final_volume (float): Desired volume after dilution.
    dropwise (bool): If ``True``, use dropwise addition speed.
    time (float): Time to add reagent over.
    stir (bool): If ``True``, stir vessel while adding reagent.
    stir_speed (float): Speed in RPM at which to stir at if stir is
        ``True``.
    viscous (bool): If ``True``, adapt process to handle viscous reagent,
        e.g. use slower addition speeds.
"""
    MANDATORY_NAME = 'Dilute'

    MANDATORY_PROP_TYPES = {
        'vessel': VESSEL_PROP_TYPE,
        'reagent': REAGENT_PROP_TYPE,
        'final_volume': float,
        'dropwise': bool,
        'time': float,
        'stir': bool,
        'stir_speed': float,
        'viscous': bool,
        'current_volume': float,
        'required_volume': float,
    }

    MANDATORY_DEFAULT_PROPS = {
        'stir': False,
        'dropwise': False,
        'viscous': False,
        'time': None,
        'stir_speed': None,
        'current_volume': None,
        'required_volume': None,
    }

    MANDATORY_PROP_LIMITS = {
        'final_volume': VOLUME_PROP_LIMIT,
        'time': TIME_PROP_LIMIT,
        'stir_speed': ROTATION_SPEED_PROP_LIMIT,
    }

    @property
    def vessel_specs(self) -> Dict[str, VesselSpec]:
        return {
            'vessel': VesselSpec(stir=self.stir)
        }
