from typing import Optional
from ..utils.prop_limits import (
    TEMP_PROP_LIMIT,
    REAGENT_ROLE_PROP_LIMIT,
    PERCENT_RANGE_PROP_LIMIT,
)
from ..steps.templates import AbstractReagent
from ..constants import REAGENT_PROP_TYPE

class Reagent(AbstractReagent):
    """Class for representing a reagent used by a procedure.

    Args:
        id (str): Unique identifier containing only letters, numbers and _
        clean_type (str): ``'organic'`` or ``'aqueous'``. Used to decide what
            type of solvent should be used to clean with after reagent has been
            used.
        cas (int): CAS number of reagent as ``int``.
        use_for_cleaning (bool): Defaults to ``False``. Specifies whether
            reagent can be used as a cleaning solvent. If the reagent is
            recognised as a common solvent setting this property to ``False``
            will NOT stop it being used for cleaning.
        stir (bool): Defaults to ``False``. Specifies whether reagent
            flask should be stirred continuously.
        temp (float): Defaults to ``None``. Specifies temperature (in
            °C) to keep reagent flask at.
        role (str): Defaults to ``None``. Specifies reagent role. NOTE:
            must be a valid reagent role if specified (catalyst, reagent,
            solvent, substrate).
        last_minute_addition (str): Defaults to ``None``. Name of reagent
            that must be added to reagent flask immediately prior to addition.
        last_minute_addition_volume (float): Defaults to ``None``. Volume
            of last minute addition.
        preserve (bool): Defaults to ``False``. ``True`` if reagent is
            expensive and should be preserved when possible; ``False`` if not.
        incompatible_reagents (List[str]): Defaults to ``None``. List of
            reagents that are incompatible with this reagent and should never
            be mixed in the backbone.
        is_base (bool): Defaults to ``False``. Specifies whether reagent
            is a base. If ``True``, more thorough backbone cleaning will be
            carried out after addition of this reagent.
    """

    PROP_TYPES = {
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

    DEFAULT_PROPS = {
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

    PROP_LIMITS = {
        'role': REAGENT_ROLE_PROP_LIMIT,
        'temp': TEMP_PROP_LIMIT,
        'purity': PERCENT_RANGE_PROP_LIMIT,
    }

    def __init__(
        self,
        name: str,
        inchi: Optional[str] = 'default',
        cas: Optional[int] = 'default',
        role: Optional[str] = 'default',
        preserve: Optional[bool] = 'default',
        use_for_cleaning: Optional[bool] = 'default',
        clean_with: Optional[bool] = 'default',
        stir: Optional[bool] = 'default',
        temp: Optional[float] = 'default',
        atmosphere: Optional[str] = 'default',
        purity: Optional[float] = 'default',
        **kwargs
    ) -> None:

        super().__init__(locals())
