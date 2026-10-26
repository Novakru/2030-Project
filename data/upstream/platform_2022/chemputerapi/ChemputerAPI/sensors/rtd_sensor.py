"""
Chemputer API for the PT100 temperature sensor.

The implementation is based on the MAX31865 amplifier board, connected to the
SensorHub using SPI (with communication pins preset in the Arduino firmware).
See more details in the corresponding section of the Commanduino Library:
https://github.com/croningp/commanduino.
"""

from typing import Union, Optional

from commanduinolabware import CommanduinoLabware

from ..device import ChemputerDevice


class RTDSensor(ChemputerDevice):
    """ Controller class for the RTD PT100 temperature sensor.

    The sensor is assumed to be connected via software preset SPI pins to the
    SensorHub board. To connect several of them one needs to modify a firmware
    and assign a name and CS pin for the new device.

    Args:
        connection_mode (str): Connection mode of the SensorHub board.
        address (str, Optional): IP address for the SensorHub board.
        port (Union[str, int]): TCP- or serial port for the SensorHub
            communication.
        simulation (bool): If running in simulation mode.
        command_id (str): Device name as set in the Arduino firmware, defaults
            to "MAX".
    """

    def __init__(
            self,
            device_name: str,
            connection_mode: str,
            address: Optional[str],
            port: Union[str, int],
            simulation: bool = False,
            command_id: str = 'MAX', # default from the Commanduino demo sketch
    ) -> None:

        super().__init__(device_name)

        # configuration for Commanduino
        config = {"ios": [], "devices": {}}
        config["ios"].append(
            {
                "type": connection_mode,
                "address": address,
                "port": str(port),
            }
        )

        # Device config
        config["devices"] = {
            self.name: {
                "command_id": command_id
            }
        }

        # Device name as in the Arduino sketch
        self.command_id = command_id

        self.device = CommanduinoLabware(
            name=self.name,
            connection_mode=None,
            address=None,
            port=None,
            config=config,
            simulation=simulation
        )

        self.initialize()

    def initialize(self) -> None:
        """Initializes sensor and sets initialization_code attribute to check
            if the sensor is actually attached.

        Notes:
            <sensor>.initialization_code is None - the device wasn't
                initialized, call get_initialization_code().

            <sensor>.initialization_code == 1 - the device is found and
                the communication was established successfully.

            <sensor>.initialization_code == 0 - the device was not found or
                the communication cannot be established. Call
                get_initialization_code() to try again.
        """

        return self.device.devices[self.name].get_initialization_code()

    def get_temperature(self) -> float:
        """ Get the temperature readings.

        Returns:
            Float: temperature in Degree Celsius.
        """

        return self.device.devices[self.name].get_temp()

    def get_error_code(self) -> int:
        """ Get the fault code readings.

        Returns:
            Int: Error code. Check Adafruit MAX31865 library for meaning.
        """

        return self.device.devices[self.name].get_error_code()
