from typing import Dict
from .abstract_template import AbstractXDLElementTemplate
from ..base_steps import AbstractStep
from ...constants import VESSEL_PROP_TYPE, REAGENT_PROP_TYPE
from ...utils.prop_limits import VOLUME_PROP_LIMIT, TIME_PROP_LIMIT
from ...utils.vessels import VesselSpec

class AbstractFilterThroughStep(AbstractXDLElementTemplate, AbstractStep):
    """Filter liquid through solid, for example filtering reaction mixture
    through celite.

    Name: FilterThrough

    Mandatory props:
        from_vessel (vessel): Vessel containing liquid to be filtered through
            solid chemical.
        to_vessel (vessel): Vessel to send liquid to after it has been filtered
            through the solid chemical.
        through (reagent): Solid chemical to filter liquid through.
        eluting_solvent (reagent): Solvent to elute with.
        eluting_volume (float): Volume of eluting_solvent to use.
        eluting_repeats (int): Number of elutions to perform.
        residence_time (float): Residence time of liquid in cartridge containing
            solid. If not given, default move speed is used.
    """
    MANDATORY_NAME = 'FilterThrough'

    MANDATORY_PROP_TYPES = {
        'from_vessel': VESSEL_PROP_TYPE,
        'to_vessel': VESSEL_PROP_TYPE,
        'through': str,
        'eluting_solvent': REAGENT_PROP_TYPE,
        'eluting_volume': float,
        'eluting_repeats': int,
        'residence_time': float,
    }

    MANDATORY_DEFAULT_PROPS = {
        'eluting_solvent': None,
        'eluting_volume': None,
        'eluting_repeats': None,
        'residence_time': None,
    }

    MANDATORY_PROP_LIMITS = {
        'eluting_volume': VOLUME_PROP_LIMIT,
        'residence_time': TIME_PROP_LIMIT,
    }

    @property
    def vessel_specs(self) -> Dict[str, VesselSpec]:
        return {
            'from_vessel': VesselSpec(),
            'to_vessel': VesselSpec(),
        }
