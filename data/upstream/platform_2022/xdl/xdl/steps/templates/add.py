from typing import Dict
from .abstract_template import AbstractXDLElementTemplate
from ..base_steps import AbstractStep
from ...constants import VESSEL_PROP_TYPE, REAGENT_PROP_TYPE
from ...utils.prop_limits import (
    VOLUME_PROP_LIMIT,
    ROTATION_SPEED_PROP_LIMIT,
    TIME_PROP_LIMIT,
    ADD_PURPOSE_PROP_LIMIT
)
from ...utils.vessels import VesselSpec

class AbstractAddStep(AbstractXDLElementTemplate, AbstractStep):
    """Add liquid reagent.

    Name: Add

    Mandatory props:
        vessel (vessel): Vessel to add reagent to.
        reagent (reagent): Reagent to add.
        volume (float): Volume of reagent to add.
        dropwise (bool): If ``True``, use dropwise addition speed.
        time (float): Time to add reagent over.
        stir (bool): If ``True``, stir vessel while adding reagent.
        stir_speed (float): Speed in RPM at which to stir at if stir is
            ``True``.
        viscous (bool): If ``True``, adapt process to handle viscous reagent,
            e.g. use slower addition speeds.
        purpose (str): Purpose of addition. If ``None`` assume that simply a
            reagent is being added. Roles of reagents can be specified in
            ``<Reagent>`` tag. Possible values: ``"precipitate"``,
            ``"neutralize"``, ``"basify"``, ``"acidify"`` or ``"dissolve"``.
    """
    MANDATORY_NAME = 'Add'

    MANDATORY_PROP_TYPES = {
        'vessel': VESSEL_PROP_TYPE,
        'reagent': REAGENT_PROP_TYPE,
        'volume': float,
        'dropwise': bool,
        'speed': float,
        'time': float,
        'stir': bool,
        'stir_speed': float,
        'viscous': bool,
        'purpose': str,
    }

    MANDATORY_DEFAULT_PROPS = {
        'stir': False,
        'dropwise': False,
        'speed': None,
        'viscous': False,
        'time': None,
        'stir_speed': None,
        'purpose': None,
    }

    MANDATORY_PROP_LIMITS = {
        'volume': VOLUME_PROP_LIMIT,
        'time': TIME_PROP_LIMIT,
        'stir_speed': ROTATION_SPEED_PROP_LIMIT,
        'purpose': ADD_PURPOSE_PROP_LIMIT,
    }

    @property
    def vessel_specs(self) -> Dict[str, VesselSpec]:
        return {
            'vessel': VesselSpec(stir=self.stir)
        }
