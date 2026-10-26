from typing import Dict
from .abstract_template import AbstractXDLElementTemplate
from ..base_steps import AbstractStep
from ...constants import VESSEL_PROP_TYPE, REAGENT_PROP_TYPE
from ...utils.vessels import VesselSpec
from ...utils.prop_limits import (
    MASS_PROP_LIMIT,
    ROTATION_SPEED_PROP_LIMIT,
    TIME_PROP_LIMIT,
    MOL_PROP_LIMIT,
    PropLimit
)

class AbstractAddSolidStep(AbstractXDLElementTemplate, AbstractStep):
    """Add solid reagent.

    Name: AddSolid

    Mandatory props:
        vessel (vessel): Vessel to add reagent to.
        reagent (reagent): Reagent to add.
        mass (float): Mass of reagent to add.
        time (float): Time to add reagent over.
        portions (int): Number of portions to add reagent in.
        stir (bool): If ``True``, stir vessel while adding reagent.
        stir_speed (float): Speed in RPM at which to stir at if stir is
            ``True``.
    """
    MANDATORY_NAME = 'AddSolid'

    MANDATORY_PROP_TYPES = {
        'vessel': VESSEL_PROP_TYPE,
        'reagent': REAGENT_PROP_TYPE,
        'mass': float,
        'mol': float,
        'time': float,
        'portions': int,
        'stir': bool,
        'stir_speed': float,
    }

    MANDATORY_DEFAULT_PROPS = {
        'mol': None,
        'stir': False,
        'time': None,
        'portions': 1,
        'stir_speed': None
    }

    MANDATORY_PROP_LIMITS = {
        'mol': MOL_PROP_LIMIT,
        'mass': MASS_PROP_LIMIT,
        'time': TIME_PROP_LIMIT,
        'stir_speed': ROTATION_SPEED_PROP_LIMIT,
    }

    @property
    def vessel_specs(self) -> Dict[str, VesselSpec]:
        return {
            'vessel': VesselSpec(stir=self.stir)
        }

class AbstractAddSolidFromDispenser(AbstractXDLElementTemplate, AbstractStep):
    """Add solid reagent from a Solid Dispenser

    Mandatory Props:
        vessel (vessel): Vessel to add reagent to
        stir (bool): Stir the vessel on addition
        stir_speed (float): Stir speed in RPM for the stirring
        turns (int): Number of turns for the Solid Dispenser to move
        speed (int): Speed of the solid dispenser movement in RPM
        driver (int): Driver used to turn the motor dependent on board used.
    """

    MANDATORY_NAME = 'AddSolidFromDispenser'

    MANDATORY_PROP_TYPES = {
        'vessel': VESSEL_PROP_TYPE,
        'stir': bool,
        'stir_speed': float,
        'dispenser': str,
        'turns': int,
        'speed': int,
        'driver': int
    }

    MANDATORY_DEFAULT_PROPS = {
        'speed': 100,
        'driver': 1,
        'dispenser': None,
        'stir_speed': None,
        'stir': False
    }

    MANDATORY_PROP_LIMITS = {
        'driver': PropLimit(
            enum=['1', '2'],
            default='1'
        ),
        'speed': PropLimit(
            enum=[str(i) for i in range(1, 601)]
        ),
        'stir_speed': ROTATION_SPEED_PROP_LIMIT
    }

    @property
    def vessel_specs(self) -> Dict[str, VesselSpec]:
        return {
            'vessel': VesselSpec(stir=self.stir)
        }
