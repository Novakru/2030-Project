from .abstract_template import AbstractXDLElementTemplate
from ...utils.prop_limits import (
    REAGENT_ROLE_PROP_LIMIT, TEMP_PROP_LIMIT, PERCENT_RANGE_PROP_LIMIT)
from ...constants import REAGENT_PROP_TYPE

class AbstractReagent(AbstractXDLElementTemplate):
    """Reagent used by procedure.

    Name: Reagent

    Mandatory props:
        name (str): Name of reagent
        inchi (str): INCHI string of reagent
        cas (str): CAS number of reagent
        role (str): Role of reagent. One of ``'reagent'``, ``'substrate'``,
            ``'catalyst'``, ``'acid'``, ``'base'``, ``'solvent'``, ``'ligand'``,
            ``'quenching-agent'`` or ``'activating-agent'``.
        preserve (bool): If ``True``, reagent is expensive and should be used
            sparingly.
        use_for_cleaning (bool): If ``True``, the reagent is cheap and can be
            used for cleaning.
        clean_with (reagent): Name of another reagent that should be used when
            cleaning vessels that have come into contact with this reagent.
        stir (bool): Stir reagent flask for the entire procedure.
        temp (float): Cool (or heat) reagent flask to given temperature for the
            entire procedure.
        atmosphere (str): Store reagent under given gas for entire procedure.
        purity (float): Purity of reagent in %.
    """
    MANDATORY_NAME = 'Reagent'

    MANDATORY_PROP_TYPES = {
        'name': str,
        'inchi': str,
        'cas': int,
        'role': str,
        'preserve': bool,
        'use_for_cleaning': bool,
        'clean_with': REAGENT_PROP_TYPE,
        'stir': bool,
        'temp': float,
        'atmosphere': str,
        'purity': float,
    }

    MANDATORY_DEFAULT_PROPS = {
        'inchi': None,
        'cas': None,
        'role': 'reagent',
        'preserve': False,
        'use_for_cleaning': False,
        'clean_with': None,
        'stir': False,
        'temp': None,
        'atmosphere': None,
        'purity': None,
    }

    MANDATORY_PROP_LIMITS = {
        'role': REAGENT_ROLE_PROP_LIMIT,
        'temp': TEMP_PROP_LIMIT,
        'purity': PERCENT_RANGE_PROP_LIMIT,
    }
