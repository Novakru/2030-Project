"""
.. module:: steps_synthesis.precipitate
    :platforms: Unix, Windows
    :synopsis: XDL step to cause precipitation by changing temperature and
                stirring for some time

"""

from typing import List, Dict, Any, Optional

#  XDL
from xdl.steps.base_steps import Step
from xdl.steps.templates import AbstractPrecipitateStep
from xdl.utils.prop_limits import (
    TEMP_PROP_LIMIT,
    TIME_PROP_LIMIT,
    ROTATION_SPEED_PROP_LIMIT,
    VOLUME_PROP_LIMIT,
)
from xdl.constants import VESSEL_PROP_TYPE, REAGENT_PROP_TYPE

# Relative
from .add import Add
from ..base_step import ChemputerStep
from ..steps_utility import Stir, HeatChillToTemp

class Precipitate(ChemputerStep, AbstractPrecipitateStep):
    """Step to cause precipitation by changing temperature and stirring for some
    time.

    Args:
        vessel (str): Vessel to trigger precipitation in.
        temp (float): Optional. Temperature to chill to to cause precipitation.
            If not given room temperature is used.
        time (float): Optional.  Time to stir vessel for after temp is reached.
    """

    DEFAULT_PROPS = {
        'temp': '25°C',
        'time': '60 mins',
        'stir_speed': '400 RPM',
        'reagent': None,
        'volume': None,
        'add_time': None,
    }

    PROP_TYPES = {
        'vessel': VESSEL_PROP_TYPE,
        'temp': float,
        'time': float,
        'stir_speed': float,
        'reagent': REAGENT_PROP_TYPE,
        'volume': float,
        'add_time': float,
    }

    PROP_LIMITS = {
        'temp': TEMP_PROP_LIMIT,
        'time': TIME_PROP_LIMIT,
        'volume': VOLUME_PROP_LIMIT,
        'add_time': TIME_PROP_LIMIT,
        'stir_speed': ROTATION_SPEED_PROP_LIMIT,
    }

    def __init__(
        self,
        vessel: str,
        temp: Optional[float] = 'default',
        time: Optional[float] = 'default',
        reagent: Optional[float] = 'default',
        volume: Optional[float] = 'default',
        add_time: Optional[float] = 'default',
        stir_speed: Optional[float] = 'default',
        **kwargs,
    ) -> None:
        super().__init__(locals())

    def get_steps(self) -> List[Step]:
        """Get the list of steps/base steps to execute.

        Returns:
            List[Step]: Steps to execute.
        """

        return (
            self.get_reagent_addition_steps()
            + self.get_heat_and_stir_steps()
        )

    def get_heat_and_stir_steps(self):
        return [
            HeatChillToTemp(vessel=self.vessel, temp=self.temp, stir=True),
            Stir(
                vessel=self.vessel, time=self.time, stir_speed=self.stir_speed),
        ]

    def get_reagent_addition_steps(self):
        if self.reagent is not None:
            return [Add(
                reagent=self.reagent,
                vessel=self.vessel,
                volume=self.volume,
                time=self.add_time,
            )]
        return []

    @property
    def requirements(self) -> Dict[str, Dict[str, Any]]:
        """Get the requirements needed for this step

        Returns:
            Dict[str, Dict[str, Any]]: Step requirements
        """

        return {
            'vessel': {
                'temp': [self.temp]
            }
        }
