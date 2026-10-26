"""
.. module:: steps_utility.general
    :platforms: Unix, Windows
    :synopsis: General utility XDL steps

"""

from typing import Optional, List
from xdl.steps.base_steps import AbstractStep, Step
from ..base_step import ChemputerStep
from ..steps_base import CSetRecordingSpeed, CWait, CWaitUntil
from ...localisation import HUMAN_READABLE_STEPS
from xdl.utils.prop_limits import TIME_PROP_LIMIT

class Wait(ChemputerStep, AbstractStep):
    """Wait for given time.

    Args:
        time (int): Time in seconds
        wait_recording_speed (int): Recording speed during wait (faster) ~2000
        after_recording_speed (int): Recording speed after wait (slower) ~14
    """

    DEFAULT_PROPS = {
        'wait_recording_speed': 2000,
        'after_recording_speed': 14,
    }

    PROP_TYPES = {
        'time': float,
        'wait_recording_speed': float,
        'after_recording_speed': float
    }

    PROP_LIMITS = {
        'time': TIME_PROP_LIMIT,
    }

    def __init__(
        self,
        time: float,
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

        return [
            CSetRecordingSpeed(self.wait_recording_speed),
            CWait(self.time),
            CSetRecordingSpeed(self.after_recording_speed),
        ]

class WaitUntil(ChemputerStep, AbstractStep):
    """Waits until a specified start time has been reached. This command will
    immediately reply with an estimate of when the waiting will be finished,
    and also give regular updates indicating that it is still alive.

    Args:
        second (int): Optional. Start time in seconds
        minute (int): Optional. Start time in minutes
        day (int): Optional. Specific day of start time
        month (int): Optional. Specific month of start time
        year (int): Optional. Specific year of start time
        hour (int): Specific hour of start time
        wait_recording_speed (int): Recording speed during wait (faster) ~2000
        after_recording_speed (int): Recording speed after wait (slower) ~14
    """
    DEFAULT_PROPS = {
        'second': 0,  # seconds
        'minute': 0,  # minutes
        'day': 0,  # days
        'month': 0,  # month
        'year': 0,  # year
        'wait_recording_speed': 2000,
        'after_recording_speed': 14,
    }

    PROP_TYPES = {
        'hour': int,
        'minute': int,
        'second': int,
        'day': int,
        'month': int,
        'year': int,
        'wait_recording_speed': float,
        'after_recording_speed': float
    }

    def __init__(
        self,
        hour: int,
        second: Optional[int] = 'default',
        minute: Optional[int] = 'default',
        day: Optional[int] = 'default',
        month: Optional[int] = 'default',
        year: Optional[int] = 'default',
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

        return [
            CSetRecordingSpeed(self.wait_recording_speed),
            CWaitUntil(
                hour=self.hour,
                minute=self.minute,
                second=self.second,
                day=self.day,
                month=self.month,
                year=self.year,
            ),
            CSetRecordingSpeed(self.after_recording_speed),
        ]

    def human_readable(self, language: str = 'en') -> str:
        """Gets the human-readable text for this step

        Args:
            language (str, optional): Localisation language. Defaults to 'en'.

        Returns:
            str: Human-readable text for the step
        """

        props = self.formatted_properties()
        props.update({
            'target_datetime': self.steps[1].get_target_datetime()
        })

        return HUMAN_READABLE_STEPS['WaitUntil'][language].format(**props)
