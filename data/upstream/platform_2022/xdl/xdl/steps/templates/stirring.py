from typing import Dict
from .abstract_template import AbstractXDLElementTemplate
from ..base_steps import AbstractStep
from ...constants import VESSEL_PROP_TYPE
from ...utils.prop_limits import (
    TIME_PROP_LIMIT, ROTATION_SPEED_PROP_LIMIT, STIR_PURPOSE_PROP_LIMIT)
from ...utils.vessels import VesselSpec

class AbstractStirStep(AbstractXDLElementTemplate, AbstractStep):
    """Stir vessel for given time.

    Name: Stir

    Mandatory props:
        vessel (vessel): Vessel to stir.
        time (float): Time to stir vessel for.
        stir_speed (float): Speed in RPM at which to stir at.
        continue_stirring (bool): If ``True``, leave stirring on at end of step.
            Otherwise stop stirring at end of step.
        purpose (str): Purpose of stirring. Can be ``None`` or ``'dissolve'``.
            If ``None``, assumed stirring is just to mix reagents.
    """
    MANDATORY_NAME = 'Stir'

    MANDATORY_PROP_TYPES = {
        'vessel': VESSEL_PROP_TYPE,
        'time': float,
        'stir_speed': float,
        'purpose': str,
        'continue_stirring': bool,
    }

    MANDATORY_DEFAULT_PROPS = {
        'stir_speed': None,
        'purpose': None,
        'continue_stirring': False,
    }

    MANDATORY_PROP_LIMITS = {
        'time': TIME_PROP_LIMIT,
        'stir_speed': ROTATION_SPEED_PROP_LIMIT,
        'purpose': STIR_PURPOSE_PROP_LIMIT,
    }

    @property
    def vessel_specs(self) -> Dict[str, VesselSpec]:
        return {
            'vessel': VesselSpec(stir=True)
        }

class AbstractStartStirStep(AbstractXDLElementTemplate, AbstractStep):
    """Start stirring vessel.

    Name: StartStir

    Mandatory props:
        vessel (vessel): Vessel to start stirring.
        stir_speed (float): Speed in RPM at which to stir at.
        purpose (str): Purpose of stirring. Can be None or 'dissolve'. If None,
            assumed stirring is just to mix reagents.
    """
    MANDATORY_NAME = 'StartStir'

    MANDATORY_PROP_TYPES = {
        'vessel': VESSEL_PROP_TYPE,
        'stir_speed': float,
        'purpose': str
    }

    MANDATORY_DEFAULT_PROPS = {
        'stir_speed': None,
        'purpose': None,
    }

    MANDATORY_PROP_LIMITS = {
        'stir_speed': ROTATION_SPEED_PROP_LIMIT,
        'purpose': STIR_PURPOSE_PROP_LIMIT,
    }

    @property
    def vessel_specs(self) -> Dict[str, VesselSpec]:
        return {
            'vessel': VesselSpec(stir=True)
        }

class AbstractStopStirStep(AbstractXDLElementTemplate, AbstractStep):
    """Stop stirring given vessel.

    Name: StopStir

    Mandatory props:
        vessel (vessel): Vessel to stop stirring.
    """
    MANDATORY_NAME = 'StopStir'

    MANDATORY_PROP_TYPES = {
        'vessel': VESSEL_PROP_TYPE,
    }

    @property
    def vessel_specs(self) -> Dict[str, VesselSpec]:
        return {
            'vessel': VesselSpec(stir=True)
        }
