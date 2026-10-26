"""
.. module::steps_synthesis.column
    :platforms: Unix, Windows
    :synopsis: XDL step for purifying a material using Column Chromatography

"""

from typing import Optional, List

# XDL
from xdl.steps import Step
from xdl.steps.base_steps import AbstractStep
from xdl.utils.prop_limits import VOLUME_PROP_LIMIT
from xdl.constants import VESSEL_PROP_TYPE, REAGENT_PROP_TYPE

# Relative
from .filter_through import FilterThrough
from ..base_step import ChemputerStep

class RunColumn(ChemputerStep, AbstractStep):
    """Purify using column chromatography.

    Args:
        from_vessel (str): Vessel containing mixture to purify.
        to_vessel (str): Vessel to send purified mixture to.
        column (str): Column cartridge to use for purification.
        move_speed (float): Optional. Speed with which to move liquid through
            the column.
        waste_vessel (str): Given internally. Vessel to send waste to.
        buffer_flask (str): Given internally. Vessel to use to temporarily
            transfer reaction mixture to if from_vessel and to_vessel are the
            same.
    """

    DEFAULT_PROPS = {
        'move_speed': 5,  # mL / min
        'column': None,
        'eluting_solvent': None,
        'eluting_volume': '10 mL',
        'eluting_repeats': 1,
    }

    PROP_TYPES = {
        'from_vessel': VESSEL_PROP_TYPE,
        'to_vessel': VESSEL_PROP_TYPE,
        'column': VESSEL_PROP_TYPE,
        'move_speed': float,
        'buffer_flask': str,
        'eluting_solvent': REAGENT_PROP_TYPE,
        'eluting_volume': float,
        'eluting_repeats': int,
    }

    INTERNAL_PROPS = [
        'buffer_flask',
    ]

    PROP_LIMITS = {
        'eluting_volume': VOLUME_PROP_LIMIT,
    }

    def __init__(
        self,
        from_vessel: str,
        to_vessel: str,
        column: str = 'default',
        eluting_solvent: str = 'default',
        eluting_volume: float = 'default',
        eluting_repeats: int = 'default',
        move_speed: Optional[float] = 'default',

        # Internal properties
        buffer_flask: Optional[str] = None,
        **kwargs
    ) -> None:
        super().__init__(locals())

    def get_steps(self) -> List[Step]:
        """Get the list of steps/base steps to execute.

        Returns:
            List[Step]: Steps to execute.
        """

        steps = [
            FilterThrough(
                from_vessel=self.from_vessel,
                to_vessel=self.to_vessel,
                through_cartridge=self.column,
                move_speed=self.move_speed,
                eluting_repeats=self.eluting_repeats,
                eluting_solvent=self.eluting_solvent,
                eluting_volume=self.eluting_volume
            )
        ]

        return steps
