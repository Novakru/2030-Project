"""
.. module:: steps-base.sensor
    :platform: Unix, Windows
    :synopsis: Wrapper step for dynamic execution with sensor feedback

"""
# pylint: disable=unused-argument, attribute-defined-outside-init

# std lib
import time
from typing import Optional, List, Callable

# External
from networkx import MultiDiGraph
import numpy as np

# XDL
from xdl.steps.base_steps import (
    AbstractDynamicStep,
    Step,
    AbstractStep,
)

# Relative
from . import GetSensorReadings, SetSensor, ChemputerStep
from ..steps_utility.general import Wait
from ...utils.prop_limits import (
    SENSOR_READING_LIMIT,
    FILTERING_FUNCTIONS_LIMIT,
    ODD_INTS,
    SENSOR_DATA_TREND_LIMIT,
)


class DoUntil(ChemputerStep, AbstractDynamicStep):
    """ Execute the children step dynamically using feedback from given sensor.

    Args:
        sensor (str): Name of the sensor object.
        threshold (float): Threshold value to continue operation when reached.
        trend (str): Estimated data trend, for the correct threshold check.
        delay (float): Delay between measurements, in seconds, defaults to 1.
        reading (str): Name of the reading attribute, if multiple are
            read from sensor.
        num_readings (Optional, int): Number of sensor readings to analyze,
            defaults to 20.
        filtering (Optional, str): Filtering function to apply to the sensor
            readings.
        window_size (Optional, int): Window size to apply the filtering
            function.
        reading_interval (Optional, float): Time interval in seconds between
            sensor readings.
        last_timestamp (float): Given internally. Timestamp when the background
            reading thread was changed. Used for readings indexing.
    """

    INTERNAL_PROPS = [
        'last_timestamp'
    ]

    PROP_TYPES = {
        'sensor': str,
        'threshold': float,
        'trend': str,
        'delay': float,
        'reading': str,
        'children': List[Step],
        'num_readings': int,
        'filtering': str,
        'window_size': int,
        'reading_interval': float,
        'last_timestamp': float,
    }

    PROP_LIMITS = {
        'threshold': SENSOR_READING_LIMIT,
        'filtering': FILTERING_FUNCTIONS_LIMIT,
        'window_size': ODD_INTS,
        'trend': SENSOR_DATA_TREND_LIMIT,
    }

    DEFAULT_PROPS = {
        'delay': 20,
        'num_readings': 20,
        'filtering': 'median',
        'window_size': 5,
        'reading_interval': 1,
        'trend': 'ascending',
    }

    def __init__(
            self,
            sensor: str,
            threshold: float,
            children: List[Step],
            reading: str,
            delay: float = 'default',
            num_readings: int = 'default',
            filtering: str = 'default',
            window_size: int = 'default',
            reading_interval: float = 'default',
            last_timestamp: Optional[float] = None,
            trend: str = 'default',

            **kwargs
    ) -> None:
        super().__init__(locals())

        self.reset()

    def reset(self) -> None:
        """Reset step placeholders."""

        self.readings = np.array([np.nan])  # To fail the first check
        self.last_timestamp = 0

    def on_prepare_for_execution(self, graph: MultiDiGraph) -> None:
        """ Prepares the step for the execution. """

    def on_start(self) -> List[Step]:
        """ Initial child step execution. """

        steps = []

        # Setting the sensor
        steps.append(
            SetSensor(
                sensor=self.sensor,
                start=True,
                reading_interval=self.reading_interval,
                on_finish=self.on_sensor_setting,
            )
        )

        for step in self.children[0].steps:
            if step.name == 'Wait':
                return steps
            steps.append(step)

        return []

    def on_continue(self) -> List[Step]:
        """ Continue operation until reading from sensor reaches threshold. """

        # Continue waiting and measuring
        steps_to_continue = [
            Wait(time=self.delay),
            GetSensorReadings(
                sensor=self.sensor,
                reading=self.reading,
                from_timestamp=self.last_timestamp,
                filtering=self.filtering,
                window_size=self.window_size,
                on_reading=self.on_sensor_reading,
            ),
        ]

        return [] if any(self.check_end()) \
            else steps_to_continue

    def on_finish(self) -> List[Step]:
        """ Last steps of the child step. """

        steps = []

        k = len(self.children[0].steps)

        for i, step in enumerate(self.children[0].steps):
            if i > k:
                steps.append(step)
            if step.name == 'Wait':
                k = i

        # Returning background thread to default
        steps.append(
            SetSensor(
                sensor=self.sensor,
                start=False,
            )
        )

        return steps

    def get_simulation_steps(self) -> List[Step]:
        """Go through on_start, on_continue and on_finish steps."""

        # Forcing threshold to skip infinite loop
        self.threshold = 0

        start_steps = self.on_start()
        continue_steps = self.on_continue()
        finish_steps = self.on_finish()

        # Stop background thread
        last_step = [SetSensor(
            sensor=self.sensor,
            stop=True,
        )]

        return start_steps + continue_steps + finish_steps + last_step

    def check_end(self) -> List[bool]:
        """ Check if the process has come to an end.

        Returns:
            List[bool]: List of boolean arguments for each termination check.
        """

        # By defalt assuming that the process hasn't ended
        checks = [False]

        # Simple check against the threshold
        checks.append(self.threshold_check())

        return checks

    def threshold_check(self) -> bool:
        """Simple check of the readings vs. threshold."""

        self.logger.info("Checking %f vs the threshold %f",
                         self.readings.mean(), self.threshold)

        if self.trend == 'ascending':
            return self.readings.mean() > self.threshold

        return self.readings.mean() < self.threshold

    def on_sensor_setting(self, timestamp: float) -> None:
        """Callback function to update the timestamp when the sensor
            background thread has started.

        Args:
            timestamp (float): Timestamp when the background reading thread
                was changed. Used for readings indexing.
        """

        self.last_timestamp = timestamp

    def on_sensor_reading(self, readings: np.ndarray) -> None:
        """ Callback function to update the readings from the sensor.

        Args:
            reading (np.ndarray): Array of sensor readings.
        """

        self.logger.debug('Obtained readings from sensor\n%s', readings)

        # Updating placeholder
        self.readings = readings

        # Updating timestamp to get the next readings array
        self.last_timestamp = time.time()

class TakeBackgroundReading(ChemputerStep, AbstractStep):
    """Take a one shot reading and pass it to callback function.

    Copies the functionality of the read sensor/get sensor readings, but
    during the procedure preparation the callback is assigned to change certain
    properties in the subsequent steps. For example, ambient temperature can
    be passed to subsequent cooling to rt step or background color readings ->
    to corresponding dynamic execution.

    Args:
        sensor (str): Node name of the sensor.
        reading (str): Name of the reading for the corresponding sensor.
        on_reading (Optional, Callable): Callback function to accept the
            reading.
        start_timestamp (float): Timestamp of the step execution to acquire the
            sensor data.
    """

    PROP_TYPES = {
        'sensor': str,
        'reading': str,
        'on_reading': Callable[[np.ndarray], None],
        'start_timestamp': float,
    }

    DEFAULT_PROPS = {
        'on_reading': None,
    }

    INTERNAL_PROPS = [
        'start_timestamp'
    ]

    def __init__(
        self,
        sensor: str,
        reading: str,
        on_reading: Callable[[float], None] = 'default',
        start_timestamp: float = None,

        **kwargs
    ) -> None:

        super().__init__(locals())

    def get_steps(self) -> List[Step]:
        """Return the steps to read the values from sensor."""

        steps = []

        # Starting sensor thread if not running
        steps.append(SetSensor(
            sensor=self.sensor,
            start=True,
            on_finish=self.on_sensor_start,
            reading_interval=.1,  # Just go quick
        ))

        # Average the last readings from the background readings
        # Parameters chosen arbitrary
        steps.append(GetSensorReadings(
            sensor=self.sensor,
            reading=self.reading,
            filtering='median',
            window_size=5,
            from_timestamp=self.start_timestamp,
            on_reading=self.on_sensor_readings,
        ))

        # Return back to default
        steps.append(SetSensor(
            sensor=self.sensor,
            start=False,
        ))

        return steps

    def on_sensor_start(self, timestamp: float) -> None:
        """Callback function to store the timestamp of the step execution."""

        self.start_timestamp = timestamp

    def on_sensor_readings(self, readings: np.ndarray) -> None:
        """A special callback function to average the readings before passing
            to self.on_reading.

        Args:
            readings(np.ndarray): An array of readings, as received from
                GetReadings step.
        """

        # Just pass the mean value
        self.on_reading(readings.mean())
