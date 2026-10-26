"""
.. module:: steps-base.sensor
    :platform: Unix, Windows
    :synopsis: Base steps for the Chemputer sensors

"""
# pylint: disable=unused-argument, attribute-defined-outside-init

# std lib
import time
import logging
from typing import Callable, List, Optional

# external
from networkx import MultiDiGraph

# Processing
import numpy as np
from scipy.signal import medfilt as scipy_signal_medfilt
from scipy.fft import fft as scipy_fft, ifft as scipy_ifft

# Chempiler
from chempiler.tools.errors import (
    ChempilerDoubleStartSensorThreadError,
    ChempilerStopSensorThreadBeforeStartError,
)
from chempiler.tools.sensor_reading.sensor_reader import SensorReader

# XDL
from xdl.steps.base_steps import AbstractBaseStep
from xdl.steps.utils import FTNDuration

# Relative
from . import ChemputerStep
from ...utils.prop_limits import ODD_INTS, FILTERING_FUNCTIONS_LIMIT

# For type annotations
if False:
    import Chempiler


DEFAULT_READING_INTERVAL = 2.0  # Seconds

# Filtering functions
def median_filter(
    readings: List[float],
    window_size: int = 10,
) -> np.ndarray:
    """Apply median filter to the readings.

    Args:
        readings (List): List of readings.

    Returns:
        np.ndarray[np.float32]: Numpy array of the filtered values.
    """

    return scipy_signal_medfilt(readings, window_size)


def fft_filter(
    readings: List[float],
    window_size: int = 10,
) -> np.ndarray:
    """Apply fft filter to the readings.

    Args:
        readings (List): List of readings.

    Returns:
        np.ndarray[np.float32]: Numpy array of the filtered values.
    """

    filt_data = scipy_fft(readings)

    # Define the fraction of coefficients (in each direction) we keep
    keep_fraction = 0.05

    # Call ff a copy of the original transform. Numpy arrays have a copy
    # method for this purpose.
    im_fft2 = filt_data.copy()

    # Set r and c (for two dimensional data) to be the number of rows
    # of the array.
    r = (im_fft2.shape)[0]

    # Set to zero all rows with indices between r*keep_fraction and
    # r*(1-keep_fraction):
    im_fft2[int(r * keep_fraction):int(r * (1 - keep_fraction))] = 0

    return scipy_ifft(im_fft2).real

class GetSensorReadings(ChemputerStep, AbstractBaseStep):
    """Get the last readings from the target sensor.

    Args:
        sensor (str): Name of the sensor.
        reading (str): Name of the corresponding reading.
        number_readings (Optional, int): Number of readings to acquire.
        filtering (Optional, str): Name of the filtering algorithm to apply to
            the raw readings.
        from_timestamp (Optional, float): Get the last readings from this
            timestamp.
        window_size (Optional, int): Window size to apply the filtering
            function.
        on_reading (Callable): Callback function to execute when reading is
            updated. Should accept numpy array as an argument.
    """

    PROP_TYPES = {
        'sensor': str,
        'reading': str,
        'number_readings': int,
        'filtering': str,
        'window_size': int,
        'from_timestamp': float,
        'on_reading': Callable[[np.ndarray], None],
    }

    PROP_LIMITS = {
        'filtering': FILTERING_FUNCTIONS_LIMIT,
        'window_size': ODD_INTS,
    }

    DEFAULT_PROPS = {
        'number_readings': 1,
        'on_reading': None,
        'window_size': 7,
    }

    filtering_functions = {
        'fft': fft_filter,
        'median': median_filter,
    }

    def __init__(
        self,
        sensor: str,
        reading: str,
        number_readings: int = 'default',
        filtering: Optional[str] = None,
        window_size: int = 'default',
        from_timestamp: Optional[float] = None,
        on_reading: Callable[[np.ndarray], None] = 'default',

        **kwargs
    ) -> None:

        super().__init__(locals())

    def execute(
        self,
        chempiler: 'Chempiler',
        logger: logging.Logger = None,
        level: int = 0,
    ) -> bool:

        self.logger.debug('Acquiring last %d %s readings from %s sensor',
                          self.number_readings, self.reading, self.sensor)

        sensor_reader: SensorReader = chempiler.sensor_readers[self.sensor]
        readings: List[float] = sensor_reader[self.reading]
        times: List[float] = sensor_reader.time

        # Indexing for the amount of readings
        # If timestamp is given, look for the closest value
        if self.from_timestamp is not None:
            # Wait till reading is acquired
            while len(times) < 1 or times[-1] < self.from_timestamp:
                time.sleep(sensor_reader.read_interval)
            # Find the index of the reading closest to timestamp
            reading_index = np.abs(
                np.array(times) - self.from_timestamp
            ).argmin()
        # Else return the last <number_readings> readings, 1 by default
        elif self.number_readings:
            reading_index = -self.number_readings

        # Last number_readings readings
        try:
            last_readings = readings[reading_index:]
        # Except not enough readings were acquired, just use all of them
        except IndexError:
            last_readings = readings[:]

        # Update the reading index to current length of readings
        # This is done to acquire more readings if needed for filtering
        reading_index = len(readings)

        if self.filtering is not None:
            # If not enough readings available for the correct filtering
            while len(last_readings) < self.window_size:
                # Wait till more is acquired
                time.sleep(sensor_reader.read_interval)
                last_readings = readings[reading_index:]

            last_readings = self.filtering_functions[self.filtering](
                last_readings,
                self.window_size
            )

        else:
            last_readings = np.array(last_readings)

        if self.on_reading:
            self.on_reading(last_readings)

        return True

    def duration(self, graph: MultiDiGraph) -> FTNDuration:
        """Approximate the step duration.

        Can take a while if the filtering function is waiting for more data.

        Args:
            graph (MultiDiGraph): Procedure graph.
        """

        # Calculating longest duration if filtering is applied
        if self.filtering is not None:
            longest_time = self.window_size * DEFAULT_READING_INTERVAL

        else:
            # Just list indexing, should be quick
            longest_time = .5

        # Time of python list indexing, unless filtering is applied
        return FTNDuration(.01, .1, longest_time)

class SetSensor(ChemputerStep, AbstractBaseStep):
    """Generic step to control the sensor reading execution.

    Args:
        sensor (str): Name of the sensor.
        start (bool): Start the background reading thread for the sensor.
            True by default.
        stop (bool): Stop the background reading thread for the sensor. False
            by default.
        reading_interval (float): Reading interval in seconds.
        on_finish (Callable): Callback function to execute when reading sensor
            reader is updated. Should accept float argument - the timestamp of
            the update.
    """

    PROP_TYPES = {
        'sensor': str,
        'start': bool,
        'stop': bool,
        'reading_interval': float,
        'on_finish': Callable[[float], None],
    }

    DEFAULT_PROPS = {
        'start': True,
        'stop': False,
        'reading_interval': DEFAULT_READING_INTERVAL,  # 2 seconds
        'on_finish': None,
    }

    def __init__(
        self,
        sensor: str,
        start: bool = 'default',
        stop: bool = 'default',
        reading_interval: float = 'default',
        on_finish: Callable[[float], None] = 'default',

        **kwargs
    ) -> None:

        super().__init__(locals())

    def execute(
        self,
        chempiler: 'Chempiler',
        logger: logging.Logger = None,
        level: int = 0,
    ) -> bool:

        self.logger.debug('Controlling %s sensor', self.sensor)

        sensor_reader: SensorReader = chempiler.sensor_readers[self.sensor]

        # Check for stop first
        if self.stop:
            # Stopping the sensor reader
            try:
                sensor_reader.stop()
            except ChempilerStopSensorThreadBeforeStartError:
                self.logger.info('Stopping already stopped background reading \
thread for %s', self.sensor)

            # When stopped, return
            return True

        if self.start:
            # Starting the sensor reader
            try:
                sensor_reader.start()
            except ChempilerDoubleStartSensorThreadError:
                self.logger.info('Starting already running background reading \
thread for %s', self.sensor)

        sensor_reader.change_reading_interval(self.reading_interval)

        # Ensuring the new reading acquired
        time.sleep(self.reading_interval)

        if self.on_finish:
            self.on_finish(time.time())

        return True

class ReadSensor(ChemputerStep, AbstractBaseStep):
    """Take reading from the sensor and send it to callback function.

    Args:
        sensor (str): Node name of the sensor.
        reading (str): Name of the reading for the corresponding sensor.
        on_reading (Optional, Callable): Callback function to accept the
            reading.
    """

    PROP_TYPES = {
        'sensor': str,
        'reading': str,
        'on_reading': Callable[[float], None],
    }

    DEFAULT_PROPS = {
        'on_reading': None,
    }

    def __init__(
        self,
        sensor: str,
        reading: str,
        on_reading: Callable[[float], None] = 'default',

        **kwargs
    ) -> None:

        super().__init__(locals())

    def execute(
        self,
        chempiler: 'Chempiler',
        logger: logging.Logger = None,
        level: int = 0,
    ) -> bool:

        self.logger.debug('Acquiring %s reading from %s sensor',
                          self.reading, self.sensor)

        sensor_reader: SensorReader = chempiler.sensor_readers[self.sensor]

        # If the sensor thread is running, just pick the latest reading
        if sensor_reader._reading_thread is not None \
                and sensor_reader._reading_thread.is_alive():
            # Waiting for at least 1 reading to arrive
            while len(sensor_reader[self.reading]) < 1:
                time.sleep(sensor_reader.read_interval)

            reading: float = sensor_reader[self.reading][-1]

        else:
            # Just one shot call for the reading
            with sensor_reader.sensor_object_lock:
                reading: float = sensor_reader.reading_functions[self.reading](
                    sensor_reader.sensor_object
                )

        if self.on_reading:
            self.on_reading(reading)
        else:
            self.logger.info(reading)

        return True
