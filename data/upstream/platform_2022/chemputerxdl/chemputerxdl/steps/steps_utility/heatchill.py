"""
.. module:: steps_utility.heatchill
    :platforms: Unix, Windows
    :synopsis: XDL steps dealing with Heating and Chilling reaction vessels

"""

from typing import Optional, List, Dict, Any
from networkx import MultiDiGraph

# XDL
from xdl.steps.base_steps import AbstractStep, Step
from xdl.steps.utils import FTNDuration
from xdl.steps.templates import (
    AbstractHeatChillToTempStep,
    AbstractStopHeatChillStep,
    AbstractStartHeatChillStep,
)
from xdl.constants import ROOM_TEMPERATURE, VESSEL_PROP_TYPE
from xdl.utils.prop_limits import (
    TEMP_PROP_LIMIT, ROTATION_SPEED_PROP_LIMIT, HEATCHILL_PURPOSE_PROP_LIMIT)
from xdl.utils.misc import SanityCheck

# Relative
from .stirring import StopStir, StartStir
from .wait_for_temp import WaitForTemp
from ..base_step import ChemputerStep
from ..steps_base import (
    CSetRecordingSpeed,
    CTemperatureControllerStart,
    CTemperatureControllerSetTemp,
    CTemperatureControllerStop,
)
from ...utils.execution import get_temperature_controller, get_heater_chiller
from ...constants import (
    CHILLER_MAX_TEMP, CHILLER_MIN_TEMP, HEATER_MAX_TEMP,
    CHILLER_CLASSES, HEATER_CLASSES, ROTAVAP_CLASSES
)

def heater_chiller_sanity_checks(
    heater: str, chiller: str, temp: float
) -> List[SanityCheck]:
    """Perform sanity checks on heaters and chillers

    Args:
        heater (str): Heater to check
        chiller (str): Chiller to check
        temp (float): Temperatures to check

    Returns:
        List[SanityCheck]: List of checks to perform
    """

    checks = []

    # No heater but chiller
    if not heater and chiller:
        # Add a check for chiller temperatures
        for condition in [
            temp <= CHILLER_MAX_TEMP,
            temp >= CHILLER_MIN_TEMP
        ]:
            checks.append(
                SanityCheck(
                    condition=condition,
                    error_msg=f'{temp} is an invalid temperature for a\
 chiller.',
                )
            )

    # No chiller but heater
    if not chiller and heater:
        # Add a check for heater temperatures
        for condition in [
            temp >= 18,
            temp <= HEATER_MAX_TEMP
        ]:
            checks.append(
                SanityCheck(
                    condition=condition,
                    error_msg=f'{temp} is an invalid temperature for a heater.'
                )
            )

    # Check temperatures are within valid ranges
    checks.append(
        SanityCheck(
            condition=CHILLER_MIN_TEMP <= temp <= HEATER_MAX_TEMP,
            error_msg=f'{temp} is an invalid temperature for a heater or a\
 chiller.'
        )
    )

    return checks

class StartHeatChill(ChemputerStep, AbstractStartHeatChillStep):
    """Start heating/chilling vessel to given temp and leave heater/chiller on.
    Don't wait to reach temp.

    Args:
        vessel (str): Vessel to heat/chill.
        temp (float): Temperature to heat/chill to in degrees C.
        purpose (str): Optional purpose of step. One of 'reaction',
            'control-exotherm' or 'unstable-reagent'.
        temperature_controller (str): Node name of temperature controller.
    """

    PROP_TYPES = {
        'vessel': VESSEL_PROP_TYPE,
        'temp': float,
        'purpose': str,
        'temperature_controller': str,

    }

    DEFAULT_PROPS = {
        'purpose': None,
    }

    PROP_LIMITS = {
        'temp': TEMP_PROP_LIMIT,
        'purpose': HEATCHILL_PURPOSE_PROP_LIMIT,
    }

    INTERNAL_PROPS = [
        'temperature_controller',
    ]

    def __init__(
        self,
        vessel: str,
        temp: float,
        purpose: Optional[str] = None,

        # Internal properties
        temperature_controller: Optional[str] = None,
        **kwargs
    ) -> None:
        super().__init__(locals())

    def on_prepare_for_execution(self, graph: MultiDiGraph):
        """Prepares the current step for execution.
        Gets/sets/cleans up appropriate items in preparation for exection.

        Args:
            graph (MultiDiGraph): Chemputer Graph to check
        """
        # Obtain temperature controller node
        self.temperature_controller = get_temperature_controller(
            graph, self.vessel, self.temp)

    def get_steps(self) -> List[Step]:
        """Get the list of steps/base steps to execute.

        Returns:
            List[Step]: Steps to execute.
        """
        return [
            CTemperatureControllerSetTemp(
                self.temperature_controller, self.temp),
            CTemperatureControllerStart(self.temperature_controller),
        ]

    @property
    def requirements(self) -> Dict[str, Dict[str, Any]]:
        """Gets the requirements needed for this step.

        Returns:
            Dict[str, Dict[str, Any]]: Requirements for the step.
        """

        return {
            'vessel': {
                'heatchill': True,
                'temp': [self.temp]
            }
        }

class HeatChillSetTemp(ChemputerStep, AbstractStep):
    """Set temp on heater/chiller.

    Args:
        vessel (str): Vessel to set temp.
        temp (float): Temperature to set in degrees C.
        temperature_controller (str): Node name of temperature controller.
    """

    INTERNAL_PROPS = [
        'temperature_controller',
    ]

    PROP_TYPES = {
        'vessel': VESSEL_PROP_TYPE,
        'temp': float,
        'temperature_controller': str,
    }

    PROP_LIMITS = {
        'temp': TEMP_PROP_LIMIT,
    }

    def __init__(
        self,
        vessel: str,
        temp: float,

        # Internal properties
        temperature_controller: Optional[str] = None,
        **kwargs
    ) -> None:
        super().__init__(locals())

    def on_prepare_for_execution(self, graph: MultiDiGraph):
        """Prepares the current step for execution.
        Gets/sets/cleans up appropriate items in preparation for exection.

        Args:
            graph (MultiDiGraph): Chemputer Graph to check
        """
        # Obtain temperature controller node
        self.temperature_controller = get_temperature_controller(
            graph, self.vessel, self.temp)

    def get_steps(self) -> List[Step]:
        """Get the list of steps/base steps to execute.

        Returns:
            List[Step]: Steps to execute.
        """
        return [
            CTemperatureControllerSetTemp(
                self.temperature_controller, self.temp)
        ]

    @property
    def requirements(self) -> Dict[str, Dict[str, Any]]:
        """Gets the requirements needed for this step.

        Returns:
            Dict[str, Dict[str, Any]]: Requirements for the step.
        """
        return {
            'vessel': {
                'heatchill': True,
                'temp': [self.temp]
            }
        }

class HeatChillToTemp(ChemputerStep, AbstractHeatChillToTempStep):
    """Heat/Chill vessel to given temp.

    Args:
        vessel (str): Vessel to heat/chill.
        temp (float): Temperature to heat/chill to in degrees C.
        active (bool): If True, will actively heat/chill to the desired temp and
            leave heater/chiller on. If False, stop heating/chilling and wait
            for the temp to be reached.
        continue_heatchill (bool): If True, heating/chilling will be left on
            at end of step, even if active is False.
        stir (bool): If True, step will be stirred, otherwise False.
        stir_speed (float): Speed to stir at, only used if stir == True.
        purpose (str): Optional purpose of step. One of 'reaction',
            'control-exotherm' or 'unstable-reagent'.
        vessel_type (str): Given internally. Used to know whether to use
            heater or chiller base steps. 'filter', 'rotavap' or 'reactor'
    """

    DEFAULT_PROPS = {
        'active': True,
        'continue_heatchill': True,
        'stir': True,
        'stir_speed': '250 RPM',
        'wait_recording_speed': 2000,
        'after_recording_speed': 14,
        'purpose': None,
    }

    PROP_TYPES = {
        'vessel': VESSEL_PROP_TYPE,
        'temp': float,
        'active': bool,
        'continue_heatchill': bool,
        'stir': bool,
        'stir_speed': float,
        'purpose': str,
        'wait_recording_speed': float,
        'after_recording_speed': float,
        'temperature_controller': str,
    }

    PROP_LIMITS = {
        'temp': TEMP_PROP_LIMIT,
        'stir_speed': ROTATION_SPEED_PROP_LIMIT,
        'purpose': HEATCHILL_PURPOSE_PROP_LIMIT,
    }

    INTERNAL_PROPS = ['temperature_controller']

    ALWAYS_WRITE = [
        'stir',
    ]

    def __init__(
        self,
        vessel: str,
        temp: float,
        active: bool = 'default',
        continue_heatchill: bool = 'default',
        stir: Optional[bool] = 'default',
        stir_speed: Optional[float] = 'default',
        purpose: Optional[str] = 'default',
        wait_recording_speed: Optional[float] = 'default',
        after_recording_speed: Optional[float] = 'default',

        # Internal props
        temperature_controller: Optional[str] = None,
        **kwargs
    ) -> None:
        super().__init__(locals())

    def on_prepare_for_execution(self, graph: MultiDiGraph):
        """Prepares the current step for execution.
        Gets/sets/cleans up appropriate items in preparation for exection.

        Args:
            graph (MultiDiGraph): Chemputer Graph to check
        """
        # Obtain temperature controller node
        self.temperature_controller = get_temperature_controller(
            graph, self.vessel, self.temp)

    def sanity_checks(self, graph: MultiDiGraph):
        return [
            SanityCheck(
                condition=self.temperature_controller,
                error_msg=f'Unable to find temperature controller connected to\
 {self.vessel} that can heat/chill to {self.temp}°C.'
            )
        ]

    def get_steps(self) -> List[Step]:
        """Get the list of steps/base steps to execute.

        Returns:
            List[Step]: Steps to execute.
        """
        # Don't try and create all steps if there is no temperature controller
        if not self.temperature_controller:
            return []
        return (
            self.get_initial_stirring_steps()
            + self.get_initial_heatchill_steps()
            + self.get_wait_for_temp_steps()
            + self.get_final_heatchill_steps()
        )

    def get_wait_for_temp_steps(self) -> List[Step]:
        return [
            CSetRecordingSpeed(self.wait_recording_speed),
            WaitForTemp(self.temperature_controller),
            CSetRecordingSpeed(self.after_recording_speed),
        ]

    def get_initial_stirring_steps(self) -> List[Step]:
        if self.stir:
            return [
                StartStir(
                    vessel=self.vessel,
                    stir_speed=self.stir_speed
                )
            ]
        else:
            return [StopStir(vessel=self.vessel)]

    def get_initial_heatchill_steps(self) -> List[Step]:
        """Get the initial steps for heatchill

        Returns:
            List[Step]: HeatChill steps
        """

        # Actively running, start heating/chilling
        if self.active:
            return [StartHeatChill(vessel=self.vessel, temp=self.temp)]

        # Not active, stop heating/chilling
        else:
            return [
                HeatChillSetTemp(vessel=self.vessel, temp=self.temp),
                StopHeatChill(vessel=self.vessel)
            ]

    def get_final_heatchill_steps(self) -> Optional[List[Step]]:
        """Get the final steps for heatchill

        Returns:
            Optional[List[Step]]: HeatChill steps, none if not needed
        """

        # Inactive heatchilling, need to switch on at end
        if self.continue_heatchill and not self.active:
            return [StartHeatChill(vessel=self.vessel, temp=self.temp)]

        # Active heatchilling, need to switch off at end
        elif not self.continue_heatchill and self.active:
            return [StopHeatChill(vessel=self.vessel)]

        # Inactive leaving off, or active leaving on.
        else:
            return []

    def get_final_stirring_steps(self) -> List[Step]:
        if self.stir:
            return [StartStir(vessel=self.vessel, stir_speed=self.stir_speed)]
        else:
            return [StopStir(vessel=self.vessel)]

    @property
    def requirements(self) -> Dict[str, Dict[str, Any]]:
        """Gets the requirements needed for this step.

        Returns:
            Dict[str, Dict[str, Any]]: Requirements for the step.
        """
        return {
            'vessel': {
                'heatchill': True,
                'temp': [self.temp]
            }
        }

    def duration(self, graph: MultiDiGraph) -> FTNDuration:

        # Arbitrary fallbacks
        min_value, most_likely_value, max_value = 5 * 60, 30 * 60, 120 * 60

        # All educated guesses. Not based on measured data.
        if self.active is True and self.temp is not None:
            vessel_class = graph.nodes[self.vessel]['class']
            temp_above_rt = abs(self.temp - 25)

            if vessel_class in ROTAVAP_CLASSES:
                min_value = 6 * temp_above_rt + 30
                most_likely_value = 12 * temp_above_rt
                max_value = 24 * temp_above_rt

            elif vessel_class in HEATER_CLASSES:
                min_value = (3 * temp_above_rt) + (5 * 60)
                most_likely_value = (6 * temp_above_rt) + (10 * 60)
                max_value = (12 * temp_above_rt) + (60 * 60)

            elif vessel_class in CHILLER_CLASSES:
                min_value = (30 * temp_above_rt) + (10 * 60)
                most_likely_value = (60 * temp_above_rt) + (30 * 60)
                max_value = (3 * 60 * temp_above_rt) + (60 * 60)

        # Passive cooling
        else:
            min_value = 30 * 60
            most_likely_value = 45 * 60
            max_value = 60 * 60

        return FTNDuration(min_value, most_likely_value, max_value)

class StopHeatChill(ChemputerStep, AbstractStopHeatChillStep):
    """Stop heater/chiller on given vessel..

    Args:
        vessel (str): Name of vessel attached to heater/chiller..
    """

    PROP_TYPES = {
        'vessel': VESSEL_PROP_TYPE,
        'heater': str,
        'chiller': str,
    }

    INTERNAL_PROPS = [
        'heater',
        'chiller'
    ]

    def __init__(
        self,
        vessel: str,

        # Internal properties
        heater: Optional[str] = None,
        chiller: Optional[str] = None,
        **kwargs
    ) -> None:
        super().__init__(locals())

    def on_prepare_for_execution(self, graph: MultiDiGraph):
        """Prepares the current step for execution.
        Gets/sets/cleans up appropriate items in preparation for exection.

        Args:
            graph (MultiDiGraph): Chemputer Graph to check
        """
        # Obtain temperature controller node
        self.heater, self.chiller = get_heater_chiller(graph, self.vessel)

    def get_steps(self) -> List[Step]:
        """Get the list of steps/base steps to execute.

        Returns:
            List[Step]: Steps to execute.
        """
        steps = []

        if self.heater:
            steps.append(CTemperatureControllerStop(self.heater))
        if self.chiller:
            steps.append(CTemperatureControllerStop(self.chiller))

        return steps

    @property
    def requirements(self) -> Dict[str, Dict[str, Any]]:
        """Gets the requirements needed for this step.

        Returns:
            Dict[str, Dict[str, Any]]: Requirements for the step.
        """
        return {
            'vessel': {
                'heatchill': True,
            }
        }

class HeatChillReturnToRT(ChemputerStep, AbstractStep):
    """Let heater/chiller return to room temperature and then stop
    heating/chilling.

    Args:
        vessel (str): Vessel to attached to heater/chiller to return to room
            temperature.
        stir (bool): If True, step will be stirred, otherwise False.
        stir_speed (float): Speed to stir at, only used if stir == True.
    """

    DEFAULT_PROPS = {
        'stir': True,
        'stir_speed': '250 RPM',
        'wait_recording_speed': 2000,
        'after_recording_speed': 14,
    }

    PROP_TYPES = {
        'vessel': VESSEL_PROP_TYPE,
        'stir': bool,
        'stir_speed': float,
        'wait_recording_speed': float,
        'after_recording_speed': float,
    }

    PROP_LIMITS = {
        'stir_speed': ROTATION_SPEED_PROP_LIMIT,
    }

    def __init__(
        self,
        vessel: str,
        stir: Optional[bool] = 'default',
        stir_speed: Optional[float] = 'default',
        wait_recording_speed: Optional[float] = 'default',
        after_recording_speed: Optional[float] = 'default',
        **kwargs
    ) -> None:
        super().__init__(locals())

    def get_steps(self) -> List[Step]:
        """Get the list of steps/base steps to execute.

        Returns:
            List[Step]: Steps to execute.
        """
        return [HeatChillToTemp(
            vessel=self.vessel,
            temp=ROOM_TEMPERATURE,
            active=False,
            continue_heatchill=False,
            stir=self.stir,
            stir_speed=self.stir_speed,
        )]
