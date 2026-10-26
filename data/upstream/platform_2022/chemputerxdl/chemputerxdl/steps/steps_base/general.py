"""
.. module:: steps_base.general
    :platforms: Unix, Windows
    :synopsis: General base steps for the Chemputer

"""

from typing import Optional, Dict, Tuple, List
from logging import Logger
import datetime
from networkx import MultiDiGraph

# XDL
from xdl.steps.base_steps import AbstractBaseStep
from xdl.steps.utils import FTNDuration
from xdl.errors import XDLError
from xdl.utils.misc import SanityCheck
from xdl.utils.prop_limits import (
    TIME_PROP_LIMIT,
    VOLUME_PROP_LIMIT,
)
from xdl.constants import VESSEL_PROP_TYPE

# Relative
from ..base_step import ChemputerStep
from ...localisation import HUMAN_READABLE_STEPS
from ...utils.prop_limits import PORT_PROP_LIMIT
from ...utils.chempiler_singleton import get_chempiler_singleton
from ...constants import CHEMPUTER_FLASK, PORT_PROP_TYPE

class Confirm(ChemputerStep, AbstractBaseStep):
    """Get the user to confirm something before execution continues.

    Args:
        msg (str): Message to get user to confirm experiment should continue.
    """

    PROP_TYPES = {
        'msg': str
    }

    def __init__(self, msg: str, **kwargs) -> None:
        super().__init__(locals())

    def locks(self, chempiler) -> Tuple[List[str], List[str], List[str]]:
        """Returns a series of locked nodes used by the Paralleliser.

        Args:
            chempiler (Chempiler): Chempiler object

        Returns:
            Tuple[List[str], List[str], List[str]]: Locked nodes in the order:
                                    1.) Current Locks -- Currently locked
                                    2.) Ongoing locks -- Continually locked
                                    3.) Unlocks -- Unlocked
        """

        return [], [], []

    def execute(
        self, chempiler, logger: Logger = None, level: int = 0
    ) -> bool:
        """Executes the XDL step.

        Args:
            chempiler (Chempiler): Chempiler object
            logger (Logger, optional): Logging object. Defaults to None.
            level (int, optional): Logging level. Defaults to 0.

        Returns:
            bool: Step executed successfully.
        """

        keep_going = input(self.msg)
        if not keep_going or keep_going.lower() in ['y', 'yes']:
            return True

        return False

class CSetRecordingSpeed(ChemputerStep, AbstractBaseStep):
    """Sets the timelapse speed of the camera module.

    Args:
        recording_speed (float): Factor by which the recording should be sped
            up, i.e. 2 would mean twice the normal speed. 1 means normal speed.
    """

    PROP_TYPES = {
        'recording_speed': float
    }

    def __init__(self, recording_speed: float, **kwargs) -> None:
        super().__init__(locals())

    def locks(self, chempiler) -> Tuple[List[str], List[str], List[str]]:
        """Returns a series of locked nodes used by the Paralleliser.

        Args:
            chempiler (Chempiler): Chempiler object

        Returns:
            Tuple[List[str], List[str], List[str]]: Locked nodes in the order:
                                    1.) Current Locks -- Currently locked
                                    2.) Ongoing locks -- Continually locked
                                    3.) Unlocks -- Unlocked
        """

        return [], [], []

    def execute(self, chempiler, logger=None, level=0) -> bool:
        """Executes the XDL step.

        Args:
            chempiler (Chempiler): Chempiler object
            logger (Logger, optional): Logging object. Defaults to None.
            level (int, optional): Logging level. Defaults to 0.

        Returns:
            bool: Step executed successfully.
        """

        chempiler.camera.change_recording_speed(self.recording_speed)
        return True

class CWait(ChemputerStep, AbstractBaseStep):
    """Delays execution of the script for a set amount of time. This command
    will immediately reply with an estimate of when the waiting will be
    finished, and also give regular updates indicating that it is still alive.

    Args:
        time (int): Time to wait in seconds.
    """

    PROP_TYPES = {
        'time': float
    }

    PROP_LIMITS = {
        'time': TIME_PROP_LIMIT,
    }

    def __init__(self, time: float, **kwargs) -> None:
        super().__init__(locals())

    def locks(self, chempiler) -> Tuple[List[str], List[str], List[str]]:
        """Returns a series of locked nodes used by the Paralleliser.

        Args:
            chempiler (Chempiler): Chempiler object

        Returns:
            Tuple[List[str], List[str], List[str]]: Locked nodes in the order:
                                    1.) Current Locks -- Currently locked
                                    2.) Ongoing locks -- Continually locked
                                    3.) Unlocks -- Unlocked
        """

        return [], [], []

    def execute(self, chempiler, logger=None, level=0) -> bool:
        """Executes the XDL step.

        Args:
            chempiler (Chempiler): Chempiler object
            logger (Logger, optional): Logging object. Defaults to None.
            level (int, optional): Logging level. Defaults to 0.

        Returns:
            bool: Step executed successfully.
        """

        chempiler.wait(self.time)
        return True

    def duration(self, graph: MultiDiGraph) -> FTNDuration:
        """Calculates the duration of the step.

        Args:
            graph (MultiDiGraph): Chempuer graph to check

        Returns:
            FTNDuration: Duration of the step.
        """

        return FTNDuration(self.time, self.time, self.time)

class CWaitUntil(ChemputerStep, AbstractBaseStep):
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
    """

    DEFAULT_PROPS = {
        'second': 0,  # seconds
        'minute': 0,  # minutes
        'day': 0,  # days
        'month': 0,  # month
        'year': 0  # year
    }

    PROP_TYPES = {
        'hour': int,
        'minute': int,
        'second': int,
        'day': int,
        'month': int,
        'year': int
    }

    def __init__(
        self,
        hour: int,
        second: Optional[int] = 'default',
        minute: Optional[int] = 'default',
        day: Optional[int] = 'default',
        month: Optional[int] = 'default',
        year: Optional[int] = 'default',
        **kwargs
    ) -> None:
        super().__init__(locals())

    def sanity_checks(self, graph: MultiDiGraph) -> List[SanityCheck]:
        """Create a series of Sanity Checks to perform for the step.

        Args:
            graph (MultiDiGraph): Chemputer graph to check

        Returns:
            List[SanityCheck]: List of Sanity checks to perform.
        """

        return [
            SanityCheck(
                condition=0 <= self.hour <= 23,
                error_msg=f'Hour property must be one of 0-23.\
 {self.hour} is invalid.'
            ),

            SanityCheck(
                condition=0 <= self.minute <= 60,
                error_msg=f'Minute property must be one of 0-59.\
 {self.minute} is invalid.'
            ),

            SanityCheck(
                condition=0 <= self.second <= 60,
                error_msg=f'Second property must be one of 0-59.\
 {self.second} is invalid.'
            ),

            SanityCheck(
                condition=0 <= self.day <= 31,
                error_msg=f'Day property must be one of 1-31.\
 {self.day} is invalid.'
            ),

            SanityCheck(
                condition=0 <= self.month <= 12,
                error_msg=f'Month property must be one of 1-12.\
 {self.month} is invalid.'
            ),

            SanityCheck(
                condition=0 <= self.year <= datetime.MAXYEAR,
                error_msg=f'Year property out of range.\
 {self.year} is invalid.'
            ),
        ]

    def get_target_datetime(self) -> Dict:
        """Get the datetime to wait until. If a date has not been specified, use
        today or tomorrow if given time has already passed today.

        Returns:
            Dict: Target datetime
        """

        today = datetime.datetime.today()

        # If date not given use today.
        if not self.day:
            year = today.year
            month = today.month
            day = today.day

            target_datetime = datetime.datetime(
                year=year,
                month=month,
                day=day,
                hour=self.hour,
                minute=self.minute,
                second=self.second
            )

            # Start time is in the past, go forward a day.
            if target_datetime < today:
                target_datetime += datetime.timedelta(days=1)

        else:
            year = self.year
            month = self.month
            day = self.day

            target_datetime = datetime.datetime(
                year=year,
                month=month,
                day=day,
                hour=self.hour,
                minute=self.minute,
                second=self.second
            )

        return target_datetime

    def get_wait_time(self) -> float:
        """Get time to wait for. Should be called at the time the step is being
        executed as it uses the current time.

        Returns:
            float: Current wait time
        """

        target_datetime = self.get_target_datetime()
        wait_time = (
            target_datetime - datetime.datetime.today()
        ).total_seconds()

        # Check not waiting until time in the past.
        if wait_time < 0:
            raise XDLError(
                f'Trying to wait until time in the past {target_datetime}.'
            )

        return wait_time

    def locks(self, chempiler) -> Tuple[List[str], List[str], List[str]]:
        """Returns a series of locked nodes used by the Paralleliser.

        Args:
            chempiler (Chempiler): Chempiler object

        Returns:
            Tuple[List[str], List[str], List[str]]: Locked nodes in the order:
                                    1.) Current Locks -- Currently locked
                                    2.) Ongoing locks -- Continually locked
                                    3.) Unlocks -- Unlocked
        """

        return [], [], []

    def execute(self, chempiler, logger=None, level=0) -> bool:
        """Executes the XDL step.

        Args:
            chempiler (Chempiler): Chempiler object
            logger (Logger, optional): Logging object. Defaults to None.
            level (int, optional): Logging level. Defaults to 0.

        Returns:
            bool: Step executed successfully.
        """

        chempiler.wait(self.get_wait_time())
        return True

    def duration(self, graph: MultiDiGraph) -> FTNDuration:
        """Calculates the duration of the step. This duration is a bit dodgy,
        because it is only valid at the time the method is called.

        Args:
            graph (MultiDiGraph): Graph to check

        Returns:
            FTNDuration: Duration of the step.
        """
        wait_time = self.get_wait_time()

        return FTNDuration(wait_time, wait_time, wait_time)

    def human_readable(self, language: str = 'en') -> str:
        """Get the human-readable version of the step.

        Args:
            language (str, optional): Localisation language. Defaults to 'en'.

        Returns:
            str: Human-readable text for the step
        """
        props = self.formatted_properties()
        props.update({
            'target_datetime': self.get_target_datetime()
        })

        return HUMAN_READABLE_STEPS['WaitUntil'][language].format(**props)

class CBreakpoint(ChemputerStep, AbstractBaseStep):
    """Introduces a breakpoint in the script. The execution is halted until the
    operator resumes it.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(locals())

    def locks(self, chempiler) -> Tuple[List[str], List[str], List[str]]:
        """Returns a series of locked nodes used by the Paralleliser.

        Args:
            chempiler (Chempiler): Chempiler object

        Returns:
            Tuple[List[str], List[str], List[str]]: Locked nodes in the order:
                                    1.) Current Locks -- Currently locked
                                    2.) Ongoing locks -- Continually locked
                                    3.) Unlocks -- Unlocked
        """

        return [], [], []

    def execute(self, chempiler, logger=None, level=0) -> bool:
        """Executes the XDL step.

        Args:
            chempiler (Chempiler): Chempiler object
            logger (Logger, optional): Logging object. Defaults to None.
            level (int, optional): Logging level. Defaults to 0.

        Returns:
            bool: Step executed successfully.
        """

        chempiler.breakpoint()
        return True

class CMove(ChemputerStep, AbstractBaseStep):
    """Moves a specified volume from one node in the graph to another. Moving
    from and to the same node is supported.

    Args:
        from_vessel (str): Vessel name to move from.
        to_vessel (str): Vessel name to move to.
        volume (float): Volume to move in mL. 'all' moves everything.
        move_speed (float): Speed at which liquid is moved in mL / min.
            (optional)
        aspiration_speed (float): Speed at which liquid aspirates from
            from_vessel. (optional)
        dispense_speed (float): Speed at which liquid dispenses from
            from_vessel. (optional)
    """

    DEFAULT_PROPS = {
        'move_speed': 40,  # mL / min
        'aspiration_speed': 40,  # mL / min
        'dispense_speed': 40,  # mL / min
        'use_backbone': True,
        'repeats': 1,
        'from_port': None,
        'to_port': None,
        'through': [],
        'unlock_after': False,
    }

    PROP_TYPES = {
        'from_vessel': str,
        'to_vessel': str,
        'volume': float,
        'move_speed': float,
        'aspiration_speed': float,
        'dispense_speed': float,
        'from_port': PORT_PROP_TYPE,
        'to_port': PORT_PROP_TYPE,
        'through': str,
        'use_backbone': bool,
        'repeats': int,
        'estimated_volume': float,
        'unlock_after': bool,
    }

    PROP_LIMITS = {
        'volume': VOLUME_PROP_LIMIT,
        'from_port': PORT_PROP_LIMIT,
        'to_port': PORT_PROP_LIMIT,
        'estimated_volume': VOLUME_PROP_LIMIT,
    }

    INTERNAL_PROPS = ['estimated_volume']

    def __init__(
        self,
        from_vessel: str,
        to_vessel: str,
        volume: float,
        move_speed: Optional[float] = 'default',
        aspiration_speed: Optional[float] = 'default',
        dispense_speed: Optional[float] = 'default',
        from_port: Optional[str] = 'default',
        to_port: Optional[str] = 'default',
        through: Optional[str] = 'default',
        use_backbone: Optional[bool] = 'default',
        repeats: Optional[int] = 'default',
        estimated_volume: Optional[float] = None,
        unlock_after: Optional[bool] = 'default',
        **kwargs
    ) -> None:
        super().__init__(locals())

    def locks(self, chempiler) -> Tuple[List[str], List[str], List[str]]:
        """Returns a series of locked nodes used by the Paralleliser.

        Args:
            chempiler (Chempiler): Chempiler object

        Returns:
            Tuple[List[str], List[str], List[str]]: Locked nodes in the order:
                                    1.) Current Locks -- Currently locked
                                    2.) Ongoing locks -- Continually locked
                                    3.) Unlocks -- Unlocked
        """
        temp_locks, ongoing_locks, unlocks = chempiler.move_locks(
            src=self.from_vessel,
            dest=self.to_vessel,
            volume=self.volume,
            initial_pump_speed=self.aspiration_speed,
            mid_pump_speed=self.move_speed,
            end_pump_speed=self.dispense_speed,
            src_port=self.from_port,
            dest_port=self.to_port,
            through_nodes=self.through,
            use_backbone=self.use_backbone,
            repeats=self.repeats,
        )
        if self.unlock_after:
            unlocks.append(self.from_vessel)

        return temp_locks, ongoing_locks, unlocks

    def execute(self, chempiler, logger=None, level=0) -> bool:
        """Executes the XDL step.

        Args:
            chempiler (Chempiler): Chempiler object
            logger (Logger, optional): Logging object. Defaults to None.
            level (int, optional): Logging level. Defaults to 0.

        Returns:
            bool: Step executed successfully.
        """
        # No acquire / release required here as it is all done within
        # `chempiler.move`.
        chempiler.move(
            src=self.from_vessel,
            dest=self.to_vessel,
            volume=self.volume,
            initial_pump_speed=self.aspiration_speed,
            mid_pump_speed=self.move_speed,
            end_pump_speed=self.dispense_speed,
            src_port=self.from_port,
            dest_port=self.to_port,
            through_nodes=self.through,
            use_backbone=self.use_backbone,
            repeats=self.repeats,
        )
        return True

    def duration(self, graph: MultiDiGraph) -> FTNDuration:
        """Gets the estimated duration of the Move step.

        Args:
            graph (MultiDiGraph): Graph to check

        Returns:
            FTNDuration: FTN duration for step.
        """
        chempiler = get_chempiler_singleton(graph)
        volume = self.volume
        if volume == 'all':
            volume = self.estimated_volume
        duration = chempiler.move_duration(
            src=self.from_vessel,
            dest=self.to_vessel,
            volume=volume,
            initial_pump_speed=self.aspiration_speed,
            mid_pump_speed=self.move_speed,
            end_pump_speed=self.dispense_speed,
            src_port=self.from_port,
            dest_port=self.to_port,
            through_nodes=self.through,
            use_backbone=self.use_backbone,
        )
        return FTNDuration(duration, duration, duration)

    def reagents_consumed(self, graph: MultiDiGraph) -> Dict:
        """Get all reagents consumed during the Move.

        Args:
            graph (MultiDiGraph): Graph to check

        Returns:
            Dict: Reagents consumed and their volumes
        """

        reagents_consumed = {}
        try:
            node = graph.nodes[self.from_vessel]
        except KeyError:
            raise KeyError(f'{self.name}\n{self.properties}')
        if node['class'] == CHEMPUTER_FLASK and node['chemical']:

            # Use vessel current_volume if volume is 'all'
            volume = self.volume
            if volume == 'all':
                volume = self.estimated_volume
            reagents_consumed[node['chemical']] = volume

        return reagents_consumed

class CConnect(ChemputerStep, AbstractBaseStep):
    """Connect two nodes together.

    Args:
        from_vessel (str): Node name to connect from.
        to_vessel (str): Node name to connect to.
        from_port (str): Port name to connect from.
        to_port (str): Port name to connect to.
        unique (bool): Must use unique route.
    """

    PROP_TYPES = {
        'from_vessel': VESSEL_PROP_TYPE,
        'to_vessel': VESSEL_PROP_TYPE,
        'from_port': PORT_PROP_TYPE,
        'to_port': PORT_PROP_TYPE,
    }

    PROP_LIMITS = {
        'from_port': PORT_PROP_LIMIT,
        'to_port': PORT_PROP_LIMIT,
    }

    DEFAULT_PROPS = {
        'from_port': None,
        'to_port': None,
    }

    def __init__(
        self,
        from_vessel: str,
        to_vessel: str,
        from_port: Optional[str] = 'default',
        to_port: Optional[str] = 'default',
        **kwargs
    ) -> None:
        super().__init__(locals())

    def locks(self, chempiler) -> Tuple[List[str], List[str], List[str]]:
        """Returns a series of locked nodes used by the Paralleliser.

        Args:
            chempiler (Chempiler): Chempiler object

        Returns:
            Tuple[List[str], List[str], List[str]]: Locked nodes in the order:
                                    1.) Current Locks -- Currently locked
                                    2.) Ongoing locks -- Continually locked
                                    3.) Unlocks -- Unlocked
        """

        return [], [], []

    def execute(self, chempiler, logger=None, level=0) -> bool:
        """Executes the XDL step.

        Args:
            chempiler (Chempiler): Chempiler object
            logger (Logger, optional): Logging object. Defaults to None.
            level (int, optional): Logging level. Defaults to 0.

        Returns:
            bool: Step executed successfully.
        """
        # No acquire / release here as it is all done within `chempiler.connect`
        chempiler.connect(
            src=self.from_vessel,
            dest=self.to_vessel,
            src_port=self.from_port,
            dest_port=self.to_port,
        )
        return True
