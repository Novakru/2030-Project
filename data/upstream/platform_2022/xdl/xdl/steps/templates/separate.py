from typing import Dict
from .abstract_template import AbstractXDLElementTemplate
from ..base_steps import AbstractStep
from ...constants import VESSEL_PROP_TYPE, REAGENT_PROP_TYPE
from ...utils.prop_limits import (
    VOLUME_PROP_LIMIT,
    SEPARATION_PRODUCT_PHASE_PROP_LIMIT,
    SEPARATION_PURPOSE_PROP_LIMIT
)
from ...utils.vessels import VesselSpec

class AbstractSeparateStep(AbstractXDLElementTemplate, AbstractStep):
    """Perform separation.

    Name: Separate

    Mandatory props:
        purpose (str): ``'wash'`` or ``'extract'``. ``'wash'`` means that
            product phase will not be the added solvent phase, ``'extract'``
            means product phase will be the added solvent phase. If no solvent
            is added just use ``'extract'``.
        product_phase (str): ``'top'`` or ``'bottom'``. Phase that product will
            be in.
        from_vessel (vessel): Contents of ``from_vessel`` are transferred to
            ``separation_vessel`` and separation is performed.
        separation_vessel (vessel): Vessel in which separation of phases will be
            carried out.
        to_vessel (vessel): Vessel to send product phase to.
        waste_phase_to_vessel (vessel): Vessel to send waste phase to.
        solvent (reagent): Solvent to add to separation vessel after contents
            of ``from_vessel`` has been transferred to create two phases.
        solvent_volume (float): Volume of solvent to add.
        through (reagent): Solid chemical to send product phase through on way
            to ``to_vessel``, e.g. ``'celite'``.
        repeats (int): Number of separations to perform.
        stir_time (float): Time stir for after adding solvent, before
            separation of phases.
        stir_speed (float): Speed to stir at after adding solvent, before
            separation of phases.
        settling_time (float): Time to allow phases to settle after stopping
            stirring, before separation of phases.
    """
    MANDATORY_NAME = 'Separate'

    MANDATORY_PROP_TYPES = {
        'purpose': str,
        'product_phase': str,
        'from_vessel': VESSEL_PROP_TYPE,
        'separation_vessel': VESSEL_PROP_TYPE,
        'to_vessel': VESSEL_PROP_TYPE,
        'waste_phase_to_vessel': VESSEL_PROP_TYPE,
        'solvent': REAGENT_PROP_TYPE,
        'solvent_volume': float,
        'through': str,
        'repeats': int,
        'stir_time': float,
        'stir_speed': float,
        'settling_time': float,
    }

    MANDATORY_DEFAULT_PROPS = {
        'waste_phase_to_vessel': None,
        'solvent': None,
        'solvent_volume': None,
        'through': None,
        'repeats': 1,
        'stir_time': None,
        'stir_speed': None,
        'settling_time': None,
    }

    MANDATORY_PROP_LIMITS = {
        'purpose': SEPARATION_PURPOSE_PROP_LIMIT,
        'product_phase': SEPARATION_PRODUCT_PHASE_PROP_LIMIT,
        'solvent_volume': VOLUME_PROP_LIMIT,
    }

    @property
    def vessel_specs(self) -> Dict[str, VesselSpec]:
        return {
            'from_vessel': VesselSpec(),
            'separation_vessel': VesselSpec(separate=True, stir=True),
            'to_vessel': VesselSpec(),
            'waste_phase_to_vessel': VesselSpec(),
        }
