"""
Chemputer API for the Cronin conductivity sensor (v 4.0).
See implementation details at
https://gitlab.com/croningroup/chemputer/chemputerhardware/conductivity-sensor
"""

from typing import Union, Optional
import threading
import time

from commanduinolabware import CommanduinoLabware

from ..device import ChemputerDevice
from ..errors import ConductivitySensorInvalidReadFrequencyError


class ConductivitySensor(ChemputerDevice):
    """ Controller class for the Cronin conductivity sensor.

    Assuming using the SensorHub.

    Args:
        connection_mode (str): Connection mode of the SensorHub board.
        address (str, Optional): IP address for the SensorHub board.
        port (Union[str, int]): TCP- or serial port for the SensorHub
            communication.
        simulation (bool): If running in simulation mode.
        analog_pin (int): Analog pin, where the sensor is plugged.
        read_frequency (float): The frequency in Hz at which readings should be
            taken in the background thread.
    """

    #: Delay in seconds between MOSFET switching on and reading the sensor
    SETTLE_DELAY_AFTER_MOSFET_ON: float = 0.5

    #: Delay in seconds between MOSFET switching off and value being returned
    SETTLE_DELAY_AFTER_MOSFET_OFF: float = 0.5

    def __init__(self, device_name: str,
                 connection_mode: str,
                 address: Optional[str],
                 port: Union[str, int],
                 simulation: bool = False,
                 analog_pin: int = 1,
                 read_frequency: float = 1) -> None:

        # Set up name and logger
        super().__init__(device_name)

        # SNAR and SNSW are the commands to read from analog channel N
        # and toggle digital channel N on the sensorhub (ADC IN connector).

        # FIXME There's currently a bug in commanduino that wouldn't allow to
        # use all 8 channels simultaneously if that is needed.
        # See https://github.com/croningp/Arduino-CommandHandler/pull/1
        self.sensor_pin = f"S{analog_pin}AR"
        self.mosfet_pin = f"S{analog_pin}DW"

        # Create configuration for Commanduino
        # IO config
        config = {"ios": [], "devices": {}}
        config["ios"].append({
            "type": connection_mode,
            "address": address,
            "port": str(port)
        })
        # Devices config
        config["devices"] = {
            self.sensor_pin: {"command_id": self.sensor_pin},
            self.mosfet_pin: {"command_id": self.mosfet_pin}
        }
        self.logger.debug("Commanduino config for pneumatic panel: %s", config)

        self.device = CommanduinoLabware(name=self.name,
                                         connection_mode=None,
                                         address=None,
                                         port=None,
                                         config=config,
                                         simulation=simulation)

        # Check requested read frequency is possible
        settle_delay = (
            ConductivitySensor.SETTLE_DELAY_AFTER_MOSFET_ON
            + ConductivitySensor.SETTLE_DELAY_AFTER_MOSFET_OFF
        )
        max_possible_read_frequency = 1 / settle_delay
        if read_frequency > max_possible_read_frequency:
            raise ConductivitySensorInvalidReadFrequencyError(
                read_frequency, max_possible_read_frequency)

        # Calculate pause after each read required to achieve given read
        # frequency
        self._pause_after_read = (1 / read_frequency) - settle_delay

        # Initialize background read thread
        self._read_thread = threading.Thread(target=self.read_thread_target)
        self._background_read_stop_event = threading.Event()

    def initialize_device(self) -> None:
        """Start taking sensor readings in background thread. The reason for
        doing this rather than just taking readings when they are required, is
        that the frequency at which readings are taken affects the readings.
        Therefore, by taking them at a regular interval, and supplying them
        when necessary, readings are stabilized.
        """
        self._read_thread.start()

    def read_thread_target(self) -> None:
        """Continuously take readings at a regular interval. Stop if the stop
        event is set.
        """
        while True:
            if self._background_read_stop_event.is_set():
                return
            self._high_res_reading = self.actually_take_reading_high_res()
            self._low_res_reading = self.actually_take_reading_low_res()
            time.sleep(self._pause_after_read)

    def stop_background_readings(self) -> None:
        """Stop taking background sensor readings. There is no real reason you
        would ever want to do this, but including it here just in case
        it's ever needed for testing / development.
        """
        self._background_read_stop_event.set()
        self._read_thread.join()

    def take_reading_high_res(self) -> float:
        """Get the latest high res reading."""
        return self._high_res_reading

    def take_reading_low_res(self) -> float:
        """Get the latest low res reading."""
        return self._low_res_reading

    def take_reading_combined(self) -> float:
        """Get the latest combined high and low res reading."""
        return self._high_res_reading + self._low_res_reading

    def actually_take_reading_high_res(self) -> float:
        """Takes reading with the high value resistor in voltage divider
        (default). Generally, this method should not be used for taking readings
        outside of this class. ``take_reading_high_res`` should be used instead,
        as this returns the latest value from the background thread.
        """

        return self.device.read_analog(self.sensor_pin)

    def actually_take_reading_low_res(self) -> float:
        """Takes reading with the high value resistor shunted
        in voltage divider (MOSFET on). Generally, this method should not be
        used for taking readings outside of this class.
        ``take_reading_low_res`` should be used instead, as this returns the
        latest value from the background thread.
        """
        # Switch MOSFET on and pause
        self.device.write_digital(self.mosfet_pin, 1)
        time.sleep(ConductivitySensor.SETTLE_DELAY_AFTER_MOSFET_ON)

        # Take reading
        result = self.device.read_analog(self.sensor_pin)

        # Switch MOSFET off and pause
        self.device.write_digital(self.mosfet_pin, 0)
        time.sleep(ConductivitySensor.SETTLE_DELAY_AFTER_MOSFET_OFF)

        # Return result
        return result

    def actually_take_reading_combined(self) -> float:
        """Takes both readings (high and low) and returns a sum. Generally,
        this method should not be used for taking readings outside of this
        class. ``take_reading_combined`` should be used instead, as this returns
        the latest value from the background thread.
        """
        return (
            self.actually_take_reading_high_res()
            + self.actually_take_reading_low_res()
        )
