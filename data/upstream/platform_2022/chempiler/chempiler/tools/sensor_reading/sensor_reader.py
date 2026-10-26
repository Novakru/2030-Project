""" Support class for sensor readings. """

import csv
import threading
import logging
import time
import os
import sys

from typing import Callable, Any, Dict, List

from ..errors import (
    ChempilerStopSensorThreadBeforeStartError,
    ChempilerDoubleStartSensorThreadError
)

STANDARD_DELIMITER = ','
# Max number of errors encountered, before stop the reading thread
MAX_ERROR_COUNT = 10


class SensorReader():
    """ Helper class to handle sensor readings. """

    def __init__(
        self,
        sensor_name: str,
        sensor_object: Any,
        sensor_object_lock: threading.Lock,
        reading_functions: Dict[str, Callable],
        logger: logging.Logger,
        file_path: str,
    ) -> None:
        """ Reader constructor method

        Args:
            sensor_name (str): Sensor name on the graph. Will be used as a
                filename to store the sensor readings.
            sensor_obj (Any): Actual sensor object.
            sensor_object_lock (threading.Lock): A lock for thread-safe access
                to the sensor object within the chempiler environment.
            reading_functions (Dict[str, Callable]): Function to get the reading
                of the sensor object and the name of the corresponding reading.
            logger (logging.Logger): A logger object to log the events.
            file_path (str): Path to store the readings file.
        """

        self.sensor_name = sensor_name
        self.sensor_object = sensor_object
        self.sensor_object_lock = sensor_object_lock
        self.reading_functions = reading_functions
        self.readings_file = os.path.join(file_path, f'{self.sensor_name}.csv')

        # Loggers
        self.chempiler_logger = logger
        self.sensor_logger = self.sensor_object.logger

        # Constants
        # Read every X seconds
        self.read_interval: int = 2
        # Save every Y datapoints
        self.save_interval: int = 3

        # Flags
        self._continue_readings_flag: threading.Event = threading.Event()
        self._stop_readings_flag: threading.Event = threading.Event()

        # Main thread placeholder
        self._reading_thread: threading.Thread = None

        # Additional initializers
        self._initialize_readings()
        self._initialize_readings_file()

        # Errors catcher
        self.errors = []

    def _initialize_readings(self) -> None:
        """ Initialize attributes for each reading of the sensor. """

        # Reading will be available as self.reading = [values]
        for reading in self.reading_functions:
            setattr(self, reading, [])
        # Additionally initialize time placeholder
        self.time = []

    def _initialize_readings_file(self) -> None:
        """ Initializes readings file.

        Creates one, if not exists, and write a header.
        """

        header = ['time'] + list(self.reading_functions)

        if not os.path.isfile(self.readings_file):
            with open(self.readings_file, 'a', newline='') as fobj:
                writer = csv.writer(fobj, delimiter=STANDARD_DELIMITER)
                writer.writerow(header)

    def record_readings(self) -> None:
        """ Record the reading of the sensor device. """

        for reading in self.reading_functions:
            error_tb = None
            # Acquiring lock
            self.sensor_object_lock.acquire()
            # Calling the read function
            try:
                current_reading = self.reading_functions[reading](
                    self.sensor_object
                )
            # TODO Catch device specific exceptions
            except:  # pylint: disable=bare-except # noqa: E722
                # Gathering the exception info
                # "error_tb" will be a list of
                # [Exception value, Traceback]
                _, *error_tb = sys.exc_info()
                self.chempiler_logger.exception('Exception in %s sensor reader\
', self.sensor_name)
                # To allow comparison with floats
                current_reading = float('nan')

            # Appending
            self[reading].append(current_reading)
            # Releasing lock
            self.sensor_object_lock.release()

        # Counting exceptions only once per reading sequence
        if error_tb is not None:
            self.errors.append(error_tb)

        # Updating the time when all readings are recorded
        self.time.append(time.time())

    def dump_to_file(self, n_last_records: int = 3) -> None:
        """ Dump the readings to file.

        Args:
            n_last_recordings (int): Number of last recording to write to file.
        """

        try:
            with open(self.readings_file, 'a', newline='') as readings_file:
                writer = csv.writer(readings_file, delimiter=STANDARD_DELIMITER)
                # Building record rows, taking only n last records
                for idx in range(-n_last_records, 0):
                    record = [
                        self[reading][idx] for reading
                        in ['time'] + list(self.reading_functions)
                    ]
                    writer.writerow(record)

        except PermissionError:
            self.chempiler_logger.warn('Cannot access readings file for %s,\
skipping data recording', self.sensor_name)

    def _record_reading_handler(self) -> None:
        """ Method to handle reading record in background thread.
        """

        counter = 0

        while True:
            # Waiting if paused
            self._continue_readings_flag.wait()

            # Breaking if requested to stop
            if self._stop_readings_flag.is_set():
                self.dump_to_file(n_last_records=counter)
                break

            # Check for maximum number of errors in readings
            if len(self.errors) >= MAX_ERROR_COUNT:
                self.sensor_logger.error('Too many errors for reading %s - %d,\
stopping corresponding reading thread.', self.sensor_name, len(self.errors))
                self.dump_to_file(n_last_records=counter)
                break

            # Record readings
            self.record_readings()
            counter += 1

            # Dump to file if needed
            if counter == self.save_interval:
                self.dump_to_file(n_last_records=counter)
                counter = 0

            # Sleep for the interval time
            time.sleep(self.read_interval)

    def start(self) -> None:
        """ Start the background reading thread for a device. """

        self.chempiler_logger.info('Starting background reading thread for %s',
                                   self.sensor_name)

        if self._reading_thread is not None and self._reading_thread.is_alive():
            raise ChempilerDoubleStartSensorThreadError

        self._reading_thread = threading.Thread(
            name=f'Background recording thread for {self.sensor_name}',
            target=self._record_reading_handler
        )

        self._continue_readings_flag.set()
        self._stop_readings_flag.clear()
        self._reading_thread.start()

    def pause(self) -> None:
        """ Pause the background reading thread. """

        self.chempiler_logger.info('Sensor reading thread for %s paused',
                                   self.sensor_name)
        self._continue_readings_flag.clear()

    def resume(self) -> None:
        """ Resume the background reading thread. """

        self.chempiler_logger.info('Resuming sensor reading thread for %s',
                                   self.sensor_name)
        self._continue_readings_flag.set()

    def stop(self) -> None:
        """ Stop the background readings thread. """

        self.chempiler_logger.info('Sensor reading thread for %s stopped',
                                   self.sensor_name)

        if self._reading_thread is None:
            raise ChempilerStopSensorThreadBeforeStartError

        # Make sure thread is released from pause
        self._continue_readings_flag.set()

        self._stop_readings_flag.set()
        self._reading_thread.join()

        # Updating placeholder
        self._reading_thread = None

    def change_reading_interval(self, new_interval: int) -> None:
        """ Change reading interval. """

        self.chempiler_logger.info('Changed reading interval for %s reading \
thread to %.2f', self.sensor_name, new_interval)
        self.read_interval = new_interval

    # Magic method for easy access of the readings
    def __getitem__(self, reading: str) -> List:
        """ Returns the reading for the current sensor object.

        Args:
            reading (str): Reading name.

        Returns:
            List: List of readings.
        """

        return getattr(self, reading)
